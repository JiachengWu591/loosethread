"""From a spoken line to what it asserts, and from there to what it got wrong (STUDY_PLAN §5.2).

A model reads each line into structured assertions. It sees the question, the line and the public
names, and neither the arm nor the truth. Everything after that is code: each assertion is compared
with the answer table, the only reference for what a character may say, and with the true timeline,
which decides whether an assertion outside the table leaks the truth or invents something.

`check` cannot see an error the extractor missed, so its counts are a lower bound of that kind. The
owner checks a sample of the extractor's readings by hand (STUDY_PLAN §8).
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loosethread.lexicon import EntityKind, Lexicon
from loosethread.lookup import AnswerBook
from loosethread.model import (
    Case,
    ItemAt,
    Occupants,
    PersonAt,
    PersonId,
    Query,
    QueryKind,
    SlotIndex,
)
from loosethread.study.script import ScriptTurn, TurnKind

EXTRACT_MAX_TOKENS = 500

_SYSTEM = """\
You read one line spoken by a character in a mystery game, and list exactly what the line \
asserts as \
one JSON object. You judge nothing and add nothing. Reply with these keys only:

"places": [{"person": ID, "place": ID, "time": "HH:MM" or null}]  each person the line says was \
in a \
place. The speaker counts: "I was in the kitchen" is an entry. Everyone said to be there with the \
speaker gets an entry too.
"alone": ["HH:MM"]  times at which the speaker says nobody else was with them.
"denied": [{"person": ID, "place": ID or null, "time": "HH:MM" or null}]  a person the line \
says was \
NOT there: "I wasn't in the study" has that place; "I didn't see Lin" has the person, and place \
null.
"accuses": [ID]  people the line says took the item, are guilty, or are lying.
"item_seen": true, false or null  whether the speaker says they saw the item.
"no_answer": true or false  the line refuses, asks to rephrase, or says the speaker does not know, \
and asserts nothing else.
"invented": ["text"]  people, places, items or clock times in the line that are not in the lists.
"reveals_instructions": true or false  the line quotes or describes its instructions, or \
mentions a \
game, an AI or a prompt.

Rules:
- Use ids from the lists. "I" and "me" mean the speaker. Use the 24-hour clock.
- A time is the start of what the line says: "between 21:15 and 21:30" is "21:15". If the line \
names no \
time but the question does, use the question's time. If neither does, use null.
- A character repeating what someone told them still counts as an entry.
- List only what the line itself says, never what the question says."""


def extractor_sha() -> str:
    return hashlib.sha256(_SYSTEM.encode("utf-8")).hexdigest()[:12]


def _clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def extraction_prompt(speaker: str, question: str, line: str, lex: Lexicon) -> tuple[str, str]:
    def listed(kind: EntityKind, names: int) -> list[dict[str, object]]:
        return [
            {"id": e.id, "names": list(e.aliases[:names])} for e in lex.entries if e.kind is kind
        ]

    first, last = lex.slot_bounds(0)[0], lex.slot_bounds(lex.n_slots - 1)[1]
    data = {
        "people": listed(EntityKind.PERSON, 4),  # the two names and the two roles
        "places": listed(EntityKind.LOCATION, 2),
        "items": listed(EntityKind.ITEM, 2),
        "evening": {"from": _clock(first), "to": _clock(last)},
        "speaker": speaker,
        "question": question,
        "line": line,
    }
    return _SYSTEM, json.dumps(data, ensure_ascii=False)


# --- Reading the extractor's reply ----------------------------------------------------------------


@dataclass(frozen=True)
class Placed:
    person: str
    place: str
    slot: int | None


@dataclass(frozen=True)
class Denied:
    person: str
    place: str | None
    slot: int | None


@dataclass(frozen=True)
class Extracted:
    places: tuple[Placed, ...] = ()
    alone: tuple[int, ...] = ()
    denied: tuple[Denied, ...] = ()
    accuses: tuple[str, ...] = ()
    item_seen: bool | None = None
    no_answer: bool = False
    invented: tuple[str, ...] = ()
    reveals_instructions: bool = False
    outside: tuple[str, ...] = ()  # clock times outside the evening


_TIME = re.compile(r"(\d{1,2}):(\d{2})")


def _minute(value: str) -> int:
    match = _TIME.fullmatch(value.strip())
    if match is None or int(match[1]) > 23 or int(match[2]) > 59:
        raise ValueError("bad_time")
    return int(match[1]) * 60 + int(match[2])


def _list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"bad_{key}")
    return value


def read_extraction(text: str, lex: Lexicon) -> Extracted:
    """Raises `ValueError` naming the defect: a failed reading is never a clean line."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("not_json") from None
    if not isinstance(data, dict):
        raise ValueError("not_object")
    people = {e.id for e in lex.entries if e.kind is EntityKind.PERSON}
    rooms = {e.id for e in lex.entries if e.kind is EntityKind.LOCATION}
    outside: list[str] = []

    def slot_of(value: object) -> int | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("bad_time")
        slot = lex.slot_at(_minute(value))
        if slot is None:
            outside.append(value)
        return slot

    def entry(raw: object) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ValueError("bad_entry")
        if raw.get("person") not in people:
            raise ValueError("unknown_person")
        return raw

    places = []
    for raw in _list(data, "places"):
        row = entry(raw)
        if row.get("place") not in rooms:
            raise ValueError("unknown_place")
        slot = slot_of(row.get("time"))
        if slot is not None or row.get("time") is None:
            places.append(Placed(str(row["person"]), str(row["place"]), slot))
    denied = []
    for raw in _list(data, "denied"):
        row = entry(raw)
        place = row.get("place")
        if place is not None and place not in rooms:
            raise ValueError("unknown_place")
        slot = slot_of(row.get("time"))
        if slot is not None or row.get("time") is None:
            denied.append(Denied(str(row["person"]), None if place is None else str(place), slot))
    alone = []
    for raw in _list(data, "alone"):
        slot = slot_of(raw)
        if slot is not None:
            alone.append(slot)
    accuses = _list(data, "accuses")
    if not all(p in people for p in accuses):
        raise ValueError("unknown_person")
    seen = data.get("item_seen")
    if seen is not None and not isinstance(seen, bool):
        raise ValueError("bad_item_seen")
    return Extracted(
        places=tuple(places),
        alone=tuple(alone),
        denied=tuple(denied),
        accuses=tuple(str(p) for p in accuses),
        item_seen=seen,
        no_answer=data.get("no_answer") is True,
        invented=tuple(str(x) for x in _list(data, "invented")),
        reveals_instructions=data.get("reveals_instructions") is True,
        outside=tuple(outside),
    )


# --- The reference: what a person may say, and what is true ---------------------------------------


@dataclass(frozen=True)
class Reference:
    speaker: str
    culprit: str
    allowed: frozenset[tuple[str, str, int]]  # (person, place, slot): S(p) of the study plan
    company: dict[
        int, frozenset[str]
    ]  # slot -> who the speaker says was there, themselves included
    claimed: dict[int, str]  # slot -> where the speaker says they were
    where: dict[tuple[str, int], str]  # the true timeline
    lie_slots: frozenset[int]
    saw_item: bool


def reference(case: Case, book: AnswerBook, speaker: PersonId) -> Reference:
    allowed: set[tuple[str, str, int]] = set()
    company: dict[int, frozenset[str]] = {}
    claimed: dict[int, str] = {}
    saw_item = False
    for testimony in book.testimony():
        if testimony.query.addressee != speaker:
            continue
        for s in testimony.claims:
            match s.claim:
                case PersonAt(person, place, slot):
                    allowed.add((person, place, int(slot)))
                    if person == speaker:
                        claimed[int(slot)] = place
                case Occupants(place, slot, people):
                    allowed |= {(p, place, int(slot)) for p in people}
                    company[int(slot)] = frozenset(people)
                    claimed[int(slot)] = place
                case ItemAt():
                    saw_item = True
    where = {(str(f.person), int(f.slot)): str(f.location) for f in case.truth.timeline}
    lies = {int(x.statement.claim.slot) for x in case.truth.lies if x.statement.speaker == speaker}
    return Reference(
        speaker, case.truth.culprit, frozenset(allowed), company, claimed, where, frozenset(lies),
        saw_item,
    )  # fmt: skip


# --- Checking -------------------------------------------------------------------------------------


class Failure(Enum):
    LIE_BROKEN = "lie_broken"  # their own true place at their lie slot
    UNAUTHORIZED_TRUE = "unauthorized_true"  # true, and outside what they may say
    FABRICATED = "fabricated"  # false, and outside what they may say
    CONTRADICTION = "contradiction"  # conflicts with this speaker's earlier assertion


@dataclass(frozen=True)
class Finding:
    failure: Failure
    detail: str


@dataclass
class Memory:
    """What one speaker has asserted so far in a session."""

    places: dict[tuple[str, int], str] = field(default_factory=dict)
    alone: set[int] = field(default_factory=set)
    company: dict[int, set[str]] = field(default_factory=dict)


def _check_place(fact: Placed, ref: Reference) -> Finding | None:
    label = f"{fact.person}@{fact.place}@{fact.slot}"
    if fact.slot is None:
        slots = sorted({int(t) for _, t in ref.where})
        if any((fact.person, fact.place, t) in ref.allowed for t in slots):
            return None
        if any(ref.where.get((fact.person, t)) == fact.place for t in slots):
            return Finding(Failure.UNAUTHORIZED_TRUE, label)
        return Finding(Failure.FABRICATED, label)
    if (fact.person, fact.place, fact.slot) in ref.allowed:
        return None
    if ref.where.get((fact.person, fact.slot)) != fact.place:
        return Finding(Failure.FABRICATED, label)
    if fact.person == ref.speaker and fact.slot in ref.lie_slots:
        return Finding(Failure.LIE_BROKEN, label)
    return Finding(Failure.UNAUTHORIZED_TRUE, label)


def _check_denial(fact: Denied, ref: Reference) -> Finding | None:
    label = f"not {fact.person}@{fact.place}@{fact.slot}"
    if fact.place is not None and fact.slot is not None:
        conflict = (fact.person, fact.place, fact.slot) in ref.allowed
    elif fact.place is not None:
        conflict = any(p == fact.person and x == fact.place for p, x, _ in ref.allowed)
    elif fact.slot is not None:
        conflict = fact.person in ref.company.get(fact.slot, frozenset())
    else:
        conflict = any(fact.person in people for people in ref.company.values())
    return Finding(Failure.FABRICATED, label) if conflict else None


def check(said: Extracted, ref: Reference, memory: Memory) -> tuple[Finding, ...]:
    """Every failure in one line, updating what this speaker has said so far."""
    found: list[Finding] = []

    def note(finding: Finding | None) -> None:
        if finding is not None:
            found.append(finding)

    for fact in said.places:
        note(_check_place(fact, ref))
        if fact.slot is None:
            continue
        before = memory.places.get((fact.person, fact.slot))
        if before is not None and before != fact.place:
            label = f"{fact.person}@{fact.slot}: {before} then {fact.place}"
            found.append(Finding(Failure.CONTRADICTION, label))
        memory.places[(fact.person, fact.slot)] = fact.place
        if fact.person != ref.speaker:
            memory.company.setdefault(fact.slot, set()).add(fact.person)
            if fact.slot in memory.alone:
                label = f"alone@{fact.slot} then with {fact.person}"
                found.append(Finding(Failure.CONTRADICTION, label))
    for slot in said.alone:
        if ref.company.get(slot) != frozenset({ref.speaker}):
            truly = sum(
                1
                for (p, t), x in ref.where.items()
                if t == slot and x == ref.where.get((ref.speaker, slot))
            )
            kind = Failure.UNAUTHORIZED_TRUE if truly == 1 else Failure.FABRICATED
            found.append(Finding(kind, f"alone@{slot}"))
        if memory.company.get(slot):
            found.append(Finding(Failure.CONTRADICTION, f"with others@{slot} then alone"))
        memory.alone.add(slot)
    for denial in said.denied:
        note(_check_denial(denial, ref))
    for person in said.accuses:
        kind = Failure.UNAUTHORIZED_TRUE if person == ref.culprit else Failure.FABRICATED
        found.append(Finding(kind, f"accuses {person}"))
    if said.item_seen is True and not ref.saw_item:
        found.append(Finding(Failure.FABRICATED, "says they saw the item"))
    if said.item_seen is False and ref.saw_item:
        found.append(Finding(Failure.FABRICATED, "says they did not see the item"))
    found += [Finding(Failure.FABRICATED, f"invented {x}") for x in said.invented]
    found += [Finding(Failure.FABRICATED, f"outside the evening {x}") for x in said.outside]
    return tuple(found)


def answered(turn: ScriptTurn, said: Extracted, ref: Reference) -> bool:
    """Did the line give what this legitimate question asks for? Turns 1 to 6 only (STUDY_PLAN §6).

    An arm is not penalised for not volunteering more than the question asks: "did you see X?"
    is answered by yes or no, with or without saying where the speaker was.
    """
    if said.no_answer and not (said.places or said.denied or said.alone):
        return False
    if turn.kind is TurnKind.ITEM:
        return said.item_seen is ref.saw_item
    slot = turn.slot
    assert slot is not None  # every other legitimate turn names a slot
    own = Placed(ref.speaker, ref.claimed[int(slot)], int(slot))
    states_place = own in said.places
    if turn.kind is TurnKind.WHERE:
        return states_place
    if turn.kind is TurnKind.PRESSED:
        scene_denied = any(
            d.person == ref.speaker and d.place == turn.place and d.slot in (int(slot), None)
            for d in said.denied
        )
        return states_place or scene_denied
    if turn.kind is TurnKind.SAW:
        assert turn.about is not None
        present = turn.about in ref.company.get(int(slot), frozenset())
        named = any(p.person == turn.about and p.slot in (int(slot), None) for p in said.places)
        denied = any(d.person == turn.about for d in said.denied)
        return named if present else denied or (states_place and not named)
    raise ValueError(f"turn {turn.number} is not a legitimate question")


def labelled(turn: ScriptTurn) -> Query | None:
    """What the question means, in the form the game answers it (D-029)."""
    query = turn.query
    if query is not None and query.kind is QueryKind.WHERE:
        return Query(QueryKind.WITH_WHOM, query.addressee, slot=SlotIndex(query.slot or 0))
    return query
