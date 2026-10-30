"""Case generator: seed -> `Case` whose player view the independent solver proves uniquely solvable.

Each attempt samples a ground-truth evening (W1–W4), derives what everyone knows, places the lies
(the culprit's alibi inside the theft window; 0–2 innocent privacy lies outside it, each exposed by
evidence), writes evidence and the full testimony table, then asks the solver — which sees only the
player view — to accept or reject. Rejected attempts are retried with the next attempt number, so
the result is a pure function of (pack, seed, params).
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from loosethread.content import ContentPack, EvidenceTemplate, load_pack
from loosethread.difficulty import measure
from loosethread.lookup import AnswerBook
from loosethread.model import (
    Basis,
    Case,
    CrimeReport,
    Event,
    EventKind,
    Evidence,
    EvidenceId,
    Fact,
    Item,
    ItemAt,
    Knowledge,
    Lie,
    LieReason,
    LocalizedText,
    LocationId,
    Motive,
    Occupants,
    PersonAt,
    PersonId,
    PlayerView,
    SlotIndex,
    Statement,
    TimeSlot,
    Truth,
    World,
)
from loosethread.solver import Solver


class ContradictionRule(Enum):
    # DESIGN §10: believing every statement that evidence does not refute leaves no suspect.
    NAIVE = "naive"
    # Stricter: the uncontested statements alone leave at least two suspects.
    TRUSTING = "trusting"


class AlibiStyle(Enum):
    OCCUPIED = "occupied"  # claims a room where one or two suspects were, unseen by them
    UNREACHABLE = "unreachable"  # claims an empty room out of reach of where they were seen


class RejectReason(Enum):
    PATHS = "paths"  # no timeline meets the sampling constraints
    UNEXPOSABLE = "unexposable"  # the culprit's alibi lie has nobody to contradict it
    NOT_UNIQUE = "not_unique"  # the solver finds zero or several consistent suspects
    TOO_EASY = "too_easy"  # solvable without contradiction reasoning
    DIFFICULTY = "difficulty"  # outside the requested question range


@dataclass(frozen=True)
class GenParams:
    n_suspects: int = 5
    n_slots: int = 8
    window: int = 3
    n_evidence: int = 6
    max_privacy_lies: int = 2
    max_hearsay: int = 2
    optional_locations: bool = False
    contradiction_rule: ContradictionRule = ContradictionRule.NAIVE
    # UNREACHABLE makes the culprit's own story self-contradictory (two questions solve it), so it
    # is off by default; see D-012.
    alibi_styles: tuple[AlibiStyle, ...] = (AlibiStyle.OCCUPIED,)
    min_questions: tuple[int, int] | None = None  # inclusive range; None = no filter
    max_attempts: int = 500

    def __post_init__(self) -> None:
        checks = (
            (4 <= self.n_suspects <= 6, "n_suspects must be 4-6"),
            (6 <= self.n_slots <= 10, "n_slots must be 6-10"),
            (2 <= self.window <= 4, "window must be 2-4"),
            (self.n_slots >= self.window + 2, "n_slots must leave a slot before and after"),
            (4 <= self.n_evidence <= 8, "n_evidence must be 4-8"),
            (0 <= self.max_privacy_lies <= 2, "max_privacy_lies must be 0-2"),
            (self.max_hearsay >= 0, "max_hearsay must be >= 0"),
            (self.max_attempts >= 1, "max_attempts must be >= 1"),
            (bool(self.alibi_styles), "alibi_styles must not be empty"),
        )
        for ok, message in checks:
            if not ok:
                raise ValueError(message)


@dataclass(frozen=True)
class Generated:
    case: Case
    attempts: int
    rejections: tuple[tuple[RejectReason, int], ...]


class GenerationError(RuntimeError):
    pass


def generate(
    seed: int, params: GenParams | None = None, pack: ContentPack | None = None
) -> Generated:
    params = params or GenParams()
    pack = pack or load_pack()
    if params.n_suspects > len(pack.roster):
        raise ValueError("the pack's roster is smaller than n_suspects")
    counts: dict[RejectReason, int] = {}
    for attempt in range(params.max_attempts):
        rng = random.Random(f"loosethread:{pack.id}:{seed}:{attempt}")
        outcome = _Attempt(rng, seed, params, pack).run()
        if isinstance(outcome, Case):
            rejections = tuple(sorted(counts.items(), key=lambda kv: kv[0].value))
            return Generated(outcome, attempt + 1, rejections)
        counts[outcome] = counts.get(outcome, 0) + 1
    raise GenerationError(f"seed {seed}: no acceptable case in {params.max_attempts} attempts")


class _Attempt:
    def __init__(self, rng: random.Random, seed: int, params: GenParams, pack: ContentPack) -> None:
        self.rng, self.seed, self.params, self.pack = rng, seed, params, pack
        dropped = frozenset() if params.optional_locations else pack.optional_locations
        self.locations = pack.map_without(dropped)
        self.loc_ids = tuple(loc.id for loc in self.locations)
        self.closed = {loc.id: loc.neighbors | {loc.id} for loc in self.locations}
        self.crime = pack.crime_location
        self.n = params.n_slots
        m = pack.slot_minutes
        self.slots = tuple(
            TimeSlot(SlotIndex(i), pack.start_minute + i * m, pack.start_minute + (i + 1) * m)
            for i in range(self.n)
        )

    def run(self) -> Case | RejectReason:
        rng, params, pack = self.rng, self.params, self.pack
        entries = rng.sample(pack.roster, params.n_suspects)
        item_spec = rng.choice(pack.items)
        client = pack.client
        people = (client, *(e.person for e in entries))
        item = Item(item_spec.id, item_spec.name, owner=client.id)
        world = World(people, self.locations, self.slots, (item,))
        self.names = {p.id: p.name for p in people}

        last_seen = rng.randint(0, self.n - params.window - 2)
        discovered = last_seen + params.window + 1
        window = tuple(range(last_seen + 1, discovered))
        culprit = rng.choice(entries).person.id
        theta = rng.choice(window)
        innocents = [e.person.id for e in entries if e.person.id != culprit]
        on_map = frozenset(self.loc_ids)
        haunts = {client.id: pack.client_haunts & on_map}
        haunts.update({e.person.id: e.haunts & on_map for e in entries})

        # --- Ground-truth timeline -------------------------------------------------------------
        crime = self.crime
        plans: list[tuple[PersonId, dict[int, LocationId], dict[int, LocationId]]] = [
            (client.id, {last_seen: crime, discovered: crime}, dict.fromkeys(window, crime)),
            (
                culprit,
                {theta: crime},
                {t: crime for t in (*window, discovered) if t != theta},
            ),
            *((p, {}, dict.fromkeys(window, crime)) for p in innocents),
        ]
        crowd: list[dict[LocationId, int]] = [{} for _ in range(self.n)]
        self.pos: dict[PersonId, list[LocationId]] = {}
        for pid, fixed, forbidden in plans:
            path = self._sample_path(fixed, forbidden, crowd, window, haunts[pid])
            if path is None:
                return RejectReason.PATHS
            self.pos[pid] = path
            for t, loc in enumerate(path):
                crowd[t][loc] = crowd[t].get(loc, 0) + 1
        people_ids = tuple(p.id for p in people)
        occ = [
            {loc: frozenset(p for p in people_ids if self.pos[p][t] == loc) for loc in self.loc_ids}
            for t in range(self.n)
        ]

        # --- Lies ------------------------------------------------------------------------------
        # The culprit's alibi is exposable in one of two ways: a room where one or two people were
        # (they did not see the culprit), or a room the culprit could not have reached from where
        # they were seen just before or after (W2). The witnesses must be suspects: the client is
        # never a suspect, so a clash with the client would name the culprit outright.
        before, after = self.pos[culprit][theta - 1], self.pos[culprit][theta + 1]
        others = set(innocents)
        seen_before = bool(occ[theta - 1][before] & others)
        seen_after = bool(occ[theta + 1][after] & others)

        def crowded(loc: LocationId) -> bool:
            reachable = loc in self.closed[before] and loc in self.closed[after]
            present = occ[theta][loc]
            return reachable and client.id not in present and 1 <= len(present) <= 2

        def unreachable(loc: LocationId) -> bool:
            return not occ[theta][loc] and (
                (loc not in self.closed[before] and seen_before)
                or (loc not in self.closed[after] and seen_after)
            )

        styles = params.alibi_styles
        alibi_options = [
            loc
            for loc in self.loc_ids
            if loc != crime
            and (
                (AlibiStyle.OCCUPIED in styles and crowded(loc))
                or (AlibiStyle.UNREACHABLE in styles and unreachable(loc))
            )
        ]
        if not alibi_options:
            return RejectReason.UNEXPOSABLE
        lie_cells: dict[tuple[PersonId, int], LocationId] = {
            (culprit, theta): rng.choice(alibi_options)
        }
        privacy = self._privacy_lies(innocents, window, lie_cells)

        # --- Evidence --------------------------------------------------------------------------
        # Never hand out evidence that by itself breaks the culprit's alibi (that would make the
        # case a one-question giveaway under T2): nothing about the culprit near the window, and
        # nobody placed in the room the culprit claims during the window.
        claimed = {t: lie_cells.get((culprit, t), self.pos[culprit][t]) for t in window}
        near = range(window[0] - 1, window[-1] + 2)
        avoid = {(culprit, t) for t in near} | {
            (p, t)
            for p in people_ids
            for t in window
            if p != culprit and self.pos[p][t] == claimed[t]
        }
        evidence = self._evidence(item, client.id, last_seen, privacy, lie_cells, people_ids, avoid)

        # --- Knowledge and testimony ----------------------------------------------------------
        knowledge = self._knowledge(people_ids, occ, item, theta, lie_cells)
        lie_statements = {
            cell: Statement(cell[0], PersonAt(cell[0], loc, SlotIndex(cell[1])), Basis.WITNESSED)
            for cell, loc in lie_cells.items()
        }
        book = AnswerBook(world, knowledge, lie_statements.values())
        view = PlayerView(
            seed=self.seed,
            world=world,
            suspects=frozenset(e.person.id for e in entries),
            motives=tuple(Motive(e.person.id, e.motive) for e in entries),
            crime=CrimeReport(item.id, crime, SlotIndex(last_seen), SlotIndex(discovered)),
            evidence=evidence,
            testimony=book.testimony(),
        )

        # --- Acceptance (player view only) --------------------------------------------------------
        solver = Solver(view)
        if solver.consistent().consistent != {culprit}:
            return RejectReason.NOT_UNIQUE
        if any(
            solver.evidence_contradicts(i)
            for i, s in enumerate(solver.statements)
            if (s.source or s.speaker) == culprit and s.claim.slot in window
        ):
            return RejectReason.TOO_EASY  # evidence alone breaks the alibi
        if params.contradiction_rule is ContradictionRule.NAIVE:
            if solver.consistent(naive=True).consistent:
                return RejectReason.TOO_EASY
        else:
            contested = solver.contested()
            uncontested = [i for i in solver.all_statements() if i not in contested]
            if len(solver.consistent(uncontested).consistent) < 2:
                return RejectReason.TOO_EASY
        if params.min_questions is not None:
            low, high = params.min_questions
            if not low <= measure(view, solver).min_questions <= high:
                return RejectReason.DIFFICULTY

        lies = self._expose(solver, lie_statements, culprit)
        if lies is None:
            return RejectReason.UNEXPOSABLE
        truth = Truth(
            culprit=culprit,
            timeline=tuple(
                PersonAt(p, self.pos[p][t], SlotIndex(t)) for p in people_ids for t in range(self.n)
            ),
            item_timeline=tuple(
                ItemAt(item.id, crime if t < theta else self.pos[culprit][t], SlotIndex(t))
                for t in range(self.n)
            ),
            events=(Event(EventKind.THEFT, culprit, item.id, crime, SlotIndex(theta)),),
            knowledge=knowledge,
            lies=lies,
        )
        return Case(view, truth)

    # --- Timeline sampling -------------------------------------------------------------------

    def _sample_path(
        self,
        fixed: dict[int, LocationId],
        forbidden: dict[int, LocationId],
        crowd: Sequence[dict[LocationId, int]],
        window: Sequence[int],
        haunts: frozenset[LocationId],
    ) -> list[LocationId] | None:
        """Random walk that hits `fixed`, avoids `forbidden`, and prefers the person's haunts and
        small groups (crowds of three or more and the crime scene are rare)."""
        allowed = [
            [fixed[t]] if t in fixed else [loc for loc in self.loc_ids if forbidden.get(t) != loc]
            for t in range(self.n)
        ]
        feasible: list[set[LocationId]] = [set() for _ in range(self.n)]
        feasible[-1] = set(allowed[-1])
        for t in range(self.n - 2, -1, -1):
            feasible[t] = {loc for loc in allowed[t] if self.closed[loc] & feasible[t + 1]}
        path: list[LocationId] = []
        for t in range(self.n):
            options = [
                loc
                for loc in self.loc_ids
                if loc in feasible[t] and (not path or loc in self.closed[path[-1]])
            ]
            if not options:
                return None
            social = 3.0 if t in window else 2.0
            weights = []
            for loc in options:
                here = crowd[t].get(loc, 0)
                weight = 1.0 + (2.0 if path and loc == path[-1] else 0.0)
                weight += (3.0 if loc in haunts else 0.0) + social * min(here, 2)
                if here >= 3:
                    weight *= 0.3
                if loc == self.crime and t not in fixed:
                    weight *= 0.2
                weights.append(weight)
            path.append(self.rng.choices(options, weights)[0])
        return path

    def _privacy_lies(
        self,
        innocents: Sequence[PersonId],
        window: Sequence[int],
        lie_cells: dict[tuple[PersonId, int], LocationId],
    ) -> list[tuple[PersonId, int]]:
        """0..max innocent lies outside the window; the claimed path still obeys W2."""
        rng = self.rng
        wanted = rng.randint(0, self.params.max_privacy_lies)
        pool = list(innocents)
        rng.shuffle(pool)
        chosen: list[tuple[PersonId, int]] = []
        for pid in pool:
            if len(chosen) == wanted:
                break
            path = self.pos[pid]
            slots = [t for t in range(self.n) if t not in window and path[t] != self.crime]
            rng.shuffle(slots)
            for t in slots:
                options = [
                    loc
                    for loc in self.loc_ids
                    if loc not in (path[t], self.crime)
                    and (t == 0 or loc in self.closed[path[t - 1]])
                    and (t == self.n - 1 or loc in self.closed[path[t + 1]])
                ]
                if options:
                    lie_cells[(pid, t)] = rng.choice(options)
                    chosen.append((pid, t))
                    break
        return chosen

    # --- Evidence ------------------------------------------------------------------------------

    def _clock(self, slot: int) -> str:
        minute = self.slots[slot].start_minute + self.rng.randrange(1, self.pack.slot_minutes)
        return f"{minute // 60:02d}:{minute % 60:02d}"

    def _render(
        self, template: EvidenceTemplate, slot: int, person: PersonId, item: Item, client: PersonId
    ) -> Evidence:
        time = self._clock(slot)
        loc = next(loc for loc in self.locations if loc.id == self.pos[person][slot])
        fields_zh = {
            "person": self.names[person].zh,
            "client": self.names[client].zh,
            "item": item.name.zh,
            "location": loc.name.zh,
            "time": time,
        }
        fields_en = {
            "person": self.names[person].en,
            "client": self.names[client].en,
            "item": item.name.en,
            "location": loc.name.en,
            "time": time,
        }
        text = LocalizedText(
            zh=template.text.zh.format(**fields_zh), en=template.text.en.format(**fields_en)
        )
        facts: tuple[Fact, ...] = (PersonAt(person, loc.id, SlotIndex(slot)),)
        return Evidence(EvidenceId("?"), template.kind, facts, text)

    def _evidence(
        self,
        item: Item,
        client: PersonId,
        last_seen: int,
        privacy: Sequence[tuple[PersonId, int]],
        lie_cells: dict[tuple[PersonId, int], LocationId],
        people_ids: Sequence[PersonId],
        avoid: set[tuple[PersonId, int]],
    ) -> tuple[Evidence, ...]:
        rng = self.rng
        photo = self._render(self.pack.last_seen_template, last_seen, client, item, client)
        photo = Evidence(
            photo.id,
            photo.kind,
            (ItemAt(item.id, self.crime, SlotIndex(last_seen)), *photo.establishes),
            photo.text,
        )
        cells = list(privacy)
        pool = [
            (p, t)
            for p in people_ids
            for t in range(self.n)
            if self.pos[p][t] != self.crime and (p, t) not in lie_cells and (p, t) not in avoid
        ]
        specific = {loc for loc, _ in self.pack.evidence_templates}
        per_person = {p: sum(1 for q, _ in cells if q == p) for p in people_ids}
        while pool and len(cells) < self.params.n_evidence - 1:
            weights = [3.0 if self.pos[p][t] in specific else 1.0 for p, t in pool]
            p, t = pool.pop(rng.choices(range(len(pool)), weights)[0])
            if per_person[p] < 2:
                cells.append((p, t))
                per_person[p] += 1
        others = [
            self._render(rng.choice(self.pack.templates_for(self.pos[p][t])), t, p, item, client)
            for p, t in cells
        ]
        rng.shuffle(others)
        return tuple(
            Evidence(EvidenceId(f"E{i}"), e.kind, e.establishes, e.text)
            for i, e in enumerate((photo, *others), start=1)
        )

    # --- Knowledge --------------------------------------------------------------------------------

    def _knowledge(
        self,
        people_ids: Sequence[PersonId],
        occ: Sequence[dict[LocationId, frozenset[PersonId]]],
        item: Item,
        theta: int,
        lie_cells: dict[tuple[PersonId, int], LocationId],
    ) -> tuple[Knowledge, ...]:
        known: list[Knowledge] = []
        for p in people_ids:
            for t in range(self.n):
                loc, slot = self.pos[p][t], SlotIndex(t)
                known.append(Knowledge(p, PersonAt(p, loc, slot), Basis.WITNESSED))
                known.append(Knowledge(p, Occupants(loc, slot, occ[t][loc]), Basis.WITNESSED))
                if loc == self.crime and t < theta:
                    known.append(Knowledge(p, ItemAt(item.id, loc, slot), Basis.WITNESSED))
        # Hearsay: B told A, at a later slot they shared, where B was (as B tells it).
        talks = [
            (a, b, t)
            for a in people_ids
            for b in people_ids
            if a != b
            for t in range(self.n)
            if any(self.pos[a][u] == self.pos[b][u] for u in range(t + 1, self.n))
        ]
        wanted = min(len(talks), self.rng.randint(0, self.params.max_hearsay))
        for a, b, t in self.rng.sample(talks, wanted):
            told = lie_cells.get((b, t), self.pos[b][t])
            known.append(Knowledge(a, PersonAt(b, told, SlotIndex(t)), Basis.HEARSAY, source=b))
        return tuple(known)

    # --- Exposure ------------------------------------------------------------------------------

    def _expose(
        self,
        solver: Solver,
        lie_statements: dict[tuple[PersonId, int], Statement],
        culprit: PersonId,
    ) -> tuple[Lie, ...] | None:
        index = {s: i for i, s in enumerate(solver.statements)}
        pairs = solver.conflict_pairs()
        lies: list[Lie] = []
        for (person, _), statement in lie_statements.items():
            i = index.get(statement)
            if i is None:
                return None
            exposers: list[EvidenceId | Statement] = []
            for a, b in pairs:
                if a == i:
                    exposers.append(solver.statements[b] if isinstance(b, int) else b)
                elif b == i:
                    exposers.append(solver.statements[a])
            if not exposers:
                return None
            reason = LieReason.ALIBI if person == culprit else LieReason.PRIVACY
            lies.append(Lie(statement, reason, tuple(exposers)))
        return tuple(lies)
