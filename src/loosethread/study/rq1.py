"""RQ1: can an LLM write, in one shot, a case that meets our acceptance criteria? (STUDY_PLAN §5.1)

The world comes from a seed: people, map, slots, item, window. The model writes the rest directly in
the schema, with no repair and no retry. `read_case` turns its reply into the `PlayerView` the
solver reads. `verdict` applies the same rule the generator applies to its own cases: exactly one
consistent suspect, and at least two left when contested statements are set aside.

The difficulty filter and the "evidence alone breaks the alibi" check are not applied: the first is
a daily-game preference, and the evidence lie shape is exempt from the second.
"""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from itertools import pairwise
from typing import Any

from loosethread.case import _RULES
from loosethread.model import (
    Basis,
    Case,
    Evidence,
    EvidenceId,
    EvidenceKind,
    Fact,
    ItemAt,
    LocalizedText,
    LocationId,
    Occupants,
    PersonAt,
    PersonId,
    PlayerView,
    Query,
    QueryKind,
    SlotIndex,
    Statement,
    Testimony,
)
from loosethread.solver import Solver

MAX_TOKENS = 8000

_INSTRUCTIONS = """\
You write one case for a deduction game. The world is fixed in the JSON you receive: people, \
places \
with their map connections, time slots, the stolen item, the scene and the theft window. You write \
what happened and what everyone says. A program will check your case with a solver, so it must be \
logically exact. Reply with one JSON object and nothing else.

{
 "culprit": ID of the suspect who did it,
 "theft_slot": index of the slot of the theft, inside the window,
 "timeline": {person ID: [place ID for each slot, in order]},
 "lies": [{"person": ID, "slot": index}],
 "evidence": [{"person": ID, "place": ID, "slot": index}],
 "testimony": {person ID: [{"place": ID, "with": [person IDs]} for each slot, in order]}
}

"timeline" is the truth. "testimony" is what each person says when asked: where they were and \
who else \
was there, for every slot and every person. "lies" lists every (person, slot) where testimony \
differs \
from the truth. "evidence" is 5 to 7 facts that are always true.

The rules every case obeys. Players know them, and the solver applies them exactly:
{rules}
- The owner is not a suspect, was at the scene in the last-seen and discovered slots, and tells \
the truth.
- A statement names exactly who was in the room: everyone named was there, and nobody else was.

What the checker requires:
1. Exactly one suspect can be the culprit, using the evidence and everyone's statements, under the \
rules above. That suspect is your "culprit".
2. Solving needs a contradiction: set aside every statement that directly conflicts with another \
statement or with evidence, and at least two suspects must still be possible.
3. Innocent people never lie in the window. Each lie they tell outside it is contradicted by \
evidence.
4. The culprit's lie about the theft slot can be exposed by evidence or by someone's statement.

Direct conflict means that for one person, two items allow no common place in the same slot, or no \
possible move between neighbouring slots."""


def instructions_sha() -> str:
    return hashlib.sha256(_INSTRUCTIONS.encode("utf-8")).hexdigest()[:12]


def writing_prompt(case: Case) -> tuple[str, str]:
    view = case.view
    world = view.world
    rules = "\n".join(f"- {en}" for _, en in _RULES)
    system = _INSTRUCTIONS.replace("{rules}", rules)
    owner = next(p.id for p in world.people if p.id not in view.suspects)
    data = {
        "people": [
            {"id": p.id, "role": p.role.en, "suspect": p.id in view.suspects} for p in world.people
        ],
        "owner": owner,
        "places": [{"id": x.id, "connects_to": sorted(x.neighbors)} for x in world.locations],
        "slots": [{"index": int(s.index), "time": s.label} for s in world.slots],
        "item": world.items[0].id,
        "scene": view.crime.location,
        "last_seen_slot": int(view.crime.last_seen),
        "discovered_slot": int(view.crime.discovered),
        "window_slots": [int(t) for t in view.crime.window],
    }
    return system, json.dumps(data, ensure_ascii=False)


@dataclass(frozen=True)
class WrittenCase:
    view: PlayerView
    culprit: PersonId
    theft_slot: int
    timeline: dict[tuple[str, int], str]
    lies: frozenset[tuple[str, int]]


def _obj(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"bad_{name}")
    return value


def _seq(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"bad_{name}")
    return value


def read_case(text: str, base: Case) -> WrittenCase:
    """The reply as a checkable case, over `base`'s public world. `ValueError` names a defect."""
    try:
        data = _obj(json.loads(text), "reply")
    except json.JSONDecodeError:
        raise ValueError("not_json") from None
    view = base.view
    world = view.world
    people = [p.id for p in world.people]
    rooms = {x.id for x in world.locations}
    n = len(world.slots)

    def person(value: object) -> PersonId:
        if value not in people:
            raise ValueError("unknown_person")
        return PersonId(str(value))

    def room(value: object) -> LocationId:
        if value not in rooms:
            raise ValueError("unknown_place")
        return LocationId(str(value))

    def slot(value: object) -> SlotIndex:
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < n:
            raise ValueError("bad_slot")
        return SlotIndex(value)

    culprit = person(data.get("culprit"))
    if culprit not in view.suspects:
        raise ValueError("culprit_not_a_suspect")
    theft = slot(data.get("theft_slot"))
    raw_time = _obj(data.get("timeline"), "timeline")
    raw_said = _obj(data.get("testimony"), "testimony")
    if set(raw_time) != set(people) or set(raw_said) != set(people):
        raise ValueError("missing_person")
    timeline: dict[tuple[str, int], str] = {}
    for who in people:
        rows = _seq(raw_time[who], "timeline")
        if len(rows) != n:
            raise ValueError("bad_timeline_length")
        for t, place in enumerate(rows):
            timeline[(who, t)] = room(place)

    testimony: list[Testimony] = []
    for who in people:
        rows = _seq(raw_said[who], "testimony")
        if len(rows) != n:
            raise ValueError("bad_testimony_length")
        for t, raw in enumerate(rows):
            row = _obj(raw, "testimony_entry")
            place = room(row.get("place"))
            others = {person(p) for p in _seq(row.get("with", []), "with")}
            said = Statement(
                who,
                Occupants(place, SlotIndex(t), frozenset(others | {who})),
                Basis.WITNESSED,
            )
            query = Query(QueryKind.WITH_WHOM, who, slot=SlotIndex(t))
            testimony.append(Testimony(query, (said,)))

    item, scene, last = world.items[0].id, view.crime.location, view.crime.last_seen
    owner = next(p for p in people if p not in view.suspects)
    photo: tuple[Fact, ...] = (ItemAt(item, scene, last), PersonAt(owner, scene, last))
    evidence = [_evidence("E1", photo)]
    for i, raw in enumerate(_seq(data.get("evidence"), "evidence"), start=2):
        row = _obj(raw, "evidence_entry")
        fact = PersonAt(person(row.get("person")), room(row.get("place")), slot(row.get("slot")))
        evidence.append(_evidence(f"E{i}", (fact,)))

    lies = frozenset(
        (person(_obj(x, "lie").get("person")), int(slot(_obj(x, "lie").get("slot"))))
        for x in _seq(data.get("lies", []), "lies")
    )
    written = PlayerView(
        seed=view.seed,
        world=world,
        suspects=view.suspects,
        motives=view.motives,
        crime=view.crime,
        evidence=tuple(evidence),
        testimony=tuple(testimony),
        pack_id=view.pack_id,
    )
    return WrittenCase(written, culprit, int(theft), timeline, lies)


def _evidence(name: str, facts: tuple[Fact, ...]) -> Evidence:
    text = LocalizedText(zh="（模型写出的证物）", en="(evidence written by the model)")
    return Evidence(EvidenceId(name), EvidenceKind.RECORD, facts, text)


class Verdict(Enum):
    """Mutually exclusive, worst first (STUDY_PLAN §5.1)."""

    INVALID = "invalid"
    SELF_CONTRADICTORY = "self_contradictory"
    MULTIPLE = "multiple"
    UNIQUE_WRONG = "unique_wrong"
    TOO_EASY = "too_easy"
    ACCEPTED = "accepted"


def verdict(view: PlayerView, culprit: PersonId) -> Verdict:
    solver = Solver(view)
    consistent = solver.consistent().consistent
    if not consistent:
        return Verdict.SELF_CONTRADICTORY
    if len(consistent) > 1:
        return Verdict.MULTIPLE
    if consistent != {culprit}:
        return Verdict.UNIQUE_WRONG
    contested = solver.contested()
    uncontested = [i for i in solver.all_statements() if i not in contested]
    if len(solver.consistent(uncontested).consistent) < 2:
        return Verdict.TOO_EASY
    return Verdict.ACCEPTED


def truth_problems(written: WrittenCase) -> tuple[str, ...]:
    """Does the model's own truth hold together? A stricter secondary check: the solver reads only
    what the player sees, so a case can pass it while its stated truth breaks the game's rules."""
    view = written.view
    world = view.world
    people = [p.id for p in world.people]
    n = len(world.slots)
    neighbours = {x.id: x.neighbors | {x.id} for x in world.locations}
    where = written.timeline
    problems: list[str] = []
    for who in people:
        for t, next_t in pairwise(range(n)):
            if where[(who, next_t)] not in neighbours[LocationId(where[(who, t)])]:
                problems.append(f"W2:{who}@{next_t}")
    scene, theft = view.crime.location, written.theft_slot
    if theft not in [int(t) for t in view.crime.window]:
        problems.append("W4:theft_outside_window")
    if where[(written.culprit, theft)] != scene:
        problems.append("W4:culprit_not_at_scene")
    if any(where[(p, theft)] == scene for p in people if p != written.culprit):
        problems.append("W4:not_alone")
    for e in view.evidence:
        for f in e.establishes:
            if isinstance(f, PersonAt) and where[(f.person, int(f.slot))] != f.location:
                problems.append(f"T1:{e.id}")
    window = {int(t) for t in view.crime.window}
    culprit_lied = False
    solver = Solver(view)
    for i, s in enumerate(solver.statements):
        claim = s.claim
        assert isinstance(claim, Occupants)
        t = int(claim.slot)
        present = {p for p in people if where[(p, t)] == claim.location}
        false = s.speaker not in present or present != set(claim.people)
        if false and (s.speaker, t) not in written.lies:
            problems.append(f"undeclared_lie:{s.speaker}@{t}")
        if false and s.speaker != written.culprit and t in window:
            problems.append(f"T2:{s.speaker}@{t}")
        if false and s.speaker != written.culprit and not solver.evidence_contradicts(i):
            problems.append(f"T3:{s.speaker}@{t}")
        if false and s.speaker == written.culprit and t == theft:
            culprit_lied = True
    if not culprit_lied:
        problems.append("T4:no_alibi_lie")
    return tuple(problems)


def generator_reply(case: Case) -> str:
    """A generated case in the schema the model writes: the checker's control and its test."""
    view, truth = case.view, case.truth
    world = view.world
    n = len(world.slots)
    people = [p.id for p in world.people]
    where = {(f.person, int(f.slot)): f.location for f in truth.timeline}
    (theft,) = truth.events
    said: dict[str, list[dict[str, object]]] = {p: [] for p in people}
    for t in view.statements:
        if isinstance(t.claim, Occupants):
            others = sorted(t.claim.people - {t.speaker})
            said[t.speaker].append(
                {"slot": int(t.claim.slot), "place": t.claim.location, "with": others}
            )
    evidence = [
        {"person": f.person, "place": f.location, "slot": int(f.slot)}
        for e in view.evidence[1:]
        for f in e.establishes
        if isinstance(f, PersonAt)
    ]
    data = {
        "culprit": truth.culprit,
        "theft_slot": int(theft.slot),
        "timeline": {p: [where[(p, t)] for t in range(n)] for p in people},
        "lies": [
            {"person": x.statement.speaker, "slot": int(x.statement.claim.slot)} for x in truth.lies
        ],
        "evidence": evidence,
        "testimony": {
            p: [
                {"place": row["place"], "with": row["with"]}
                for row in sorted(said[p], key=lambda r: int(str(r["slot"])))
            ]
            for p in people
        },
    }
    return json.dumps(data)
