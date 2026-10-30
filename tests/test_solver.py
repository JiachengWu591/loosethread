"""Solver tests, including a brute-force cross-check on small random problems.

The brute force enumerates whole joint timelines and evaluates facts directly, so it shares no logic
with the solver's per-person bitmask DP. Agreement on many random problems is the main evidence that
the solver's decomposition is exact.
"""

import itertools
import random
from collections.abc import Sequence

import pytest

from loosethread.model import (
    Basis,
    CrimeReport,
    Evidence,
    EvidenceId,
    EvidenceKind,
    Fact,
    Item,
    ItemAt,
    ItemId,
    LocalizedText,
    Location,
    LocationId,
    Occupants,
    Person,
    PersonAt,
    PersonId,
    PlayerView,
    Query,
    QueryKind,
    SlotIndex,
    Statement,
    Testimony,
    TimeSlot,
    World,
)
from loosethread.solver import Solver, solve, solve_naive, solve_trusting

A, B, C = LocationId("a"), LocationId("b"), LocationId("c")  # path a-b-c; c is the crime scene
ITEM = ItemId("item")
ADJ = {A: {A, B}, B: {A, B, C}, C: {B, C}}


def _text(s: str) -> LocalizedText:
    return LocalizedText(s, s)


def _world(people: Sequence[PersonId], n_slots: int) -> World:
    return World(
        people=tuple(Person(p, _text(p), _text("r"), _text("x")) for p in people),
        locations=(
            Location(A, _text("a"), frozenset({B})),
            Location(B, _text("b"), frozenset({A, C})),
            Location(C, _text("c"), frozenset({B})),
        ),
        slots=tuple(TimeSlot(SlotIndex(i), 600 + 15 * i, 615 + 15 * i) for i in range(n_slots)),
        items=(Item(ITEM, _text("item"), None),),
    )


def _random_fact(rng: random.Random, people: Sequence[PersonId], n_slots: int) -> Fact:
    slot = SlotIndex(rng.randrange(n_slots))
    loc = rng.choice([A, B, C])
    kind = rng.random()
    if kind < 0.5:
        return PersonAt(rng.choice(people), loc, slot)
    if kind < 0.85:
        return Occupants(loc, slot, frozenset(p for p in people if rng.random() < 0.4))
    return ItemAt(ITEM, rng.choice([C, C, B]), slot)


def _random_view(rng: random.Random, n_people: int, n_slots: int) -> PlayerView:
    people = [PersonId(f"p{i}") for i in range(n_people)]
    evidence = tuple(
        Evidence(
            EvidenceId(f"E{i}"),
            EvidenceKind.RECORD,
            (_random_fact(rng, people, n_slots),),
            _text("e"),
        )
        for i in range(rng.randint(0, 2))
    )
    testimony = []
    for _ in range(rng.randint(2, 8)):
        speaker = rng.choice(people)
        if rng.random() < 0.15:
            source = rng.choice([p for p in people if p != speaker])
            fact = _random_fact(rng, people, n_slots)
            claim = Statement(speaker, fact, Basis.HEARSAY, source=source)
        else:
            claim = Statement(speaker, _random_fact(rng, people, n_slots), Basis.WITNESSED)
        query = Query(QueryKind.WHERE, speaker, slot=SlotIndex(0))
        testimony.append(Testimony(query, (claim,)))
    return PlayerView(
        seed=0,
        world=_world(people, n_slots),
        suspects=frozenset(people),
        motives=(),
        crime=CrimeReport(ITEM, C, SlotIndex(0), SlotIndex(n_slots - 1)),
        evidence=evidence,
        testimony=tuple(testimony),
    )


# --- Brute force (direct semantics, no shared code with the solver) ------------------------------


type Timeline = dict[PersonId, tuple[LocationId, ...]]
type CellSet = list[tuple[PersonId, int, set[LocationId]]]


def _paths(n_slots: int) -> list[tuple[LocationId, ...]]:
    out: list[tuple[LocationId, ...]] = [(loc,) for loc in (A, B, C)]
    for _ in range(n_slots - 1):
        out = [(*p, nxt) for p in out for nxt in sorted(ADJ[p[-1]])]
    return out


def _holds(fact: Fact, timeline: Timeline, theta: int, witness: PersonId | None) -> bool:
    match fact:
        case PersonAt(p, loc, t):
            return timeline[p][t] == loc
        case Occupants(loc, t, people):
            return {p for p, path in timeline.items() if path[t] == loc} == set(people)
        case ItemAt(item, loc, t):
            if witness is not None and timeline[witness][t] != loc:
                return False
            return not (item == ITEM and loc == C) or t < theta
    return False


def _cells(fact: Fact, people: Sequence[PersonId], witness: PersonId | None) -> CellSet:
    """The fact as per-cell allowed sets (used only for the 'contradicted by evidence' test)."""
    match fact:
        case PersonAt(p, loc, t):
            return [(p, t, {loc})]
        case Occupants(loc, t, present):
            return [(p, t, {loc} if p in present else {A, B, C} - {loc}) for p in people]
        case ItemAt(_, loc, t):
            return [] if witness is None else [(witness, t, {loc})]
    return []


def _contradicted(statement_cells: CellSet, evidence_cells: CellSet) -> bool:
    allowed: dict[tuple[PersonId, int], set[LocationId]] = {}
    for p, t, s in evidence_cells:
        allowed[(p, t)] = allowed.get((p, t), {A, B, C}) & s
    merged: dict[tuple[PersonId, int], set[LocationId]] = {}
    for p, t, s in statement_cells:
        merged[(p, t)] = merged.get((p, t), {A, B, C}) & s
    for (p, t), mine in merged.items():
        if not mine & allowed.get((p, t), {A, B, C}):
            return True
        for u in (t - 1, t + 1):
            theirs = allowed.get((p, u), {A, B, C})
            if not any(x in ADJ[y] for x in mine for y in theirs):
                return True
    return False


def _brute(view: PlayerView, active: set[int], naive: bool = False) -> frozenset[PersonId]:
    people = [p.id for p in view.world.people]
    n_slots = len(view.world.slots)
    statements = view.statements
    evidence_facts = [f for e in view.evidence for f in e.establishes]
    evidence_cells = [c for f in evidence_facts for c in _cells(f, people, None)]
    paths = _paths(n_slots)
    alive: set[PersonId] = set()
    for culprit in view.suspects:
        must = []
        for i in sorted(active):
            s = statements[i]
            source = s.source if s.basis is Basis.HEARSAY else s.speaker
            assert source is not None
            contradicted = _contradicted(_cells(s.claim, people, source), evidence_cells)
            in_window = s.claim.slot in view.crime.window
            keep = (
                (not contradicted)
                if naive
                else (source != culprit and (in_window or not contradicted))
            )
            if keep:
                must.append((s.claim, source))
        found = False
        for combo in itertools.product(paths, repeat=len(people)):
            timeline = dict(zip(people, combo, strict=True))
            for theta in view.crime.window:
                if timeline[culprit][theta] != C:
                    continue
                if any(timeline[q][theta] == C for q in people if q != culprit):
                    continue
                if not all(_holds(f, timeline, theta, None) for f in evidence_facts):
                    continue
                if all(_holds(f, timeline, theta, w) for f, w in must):
                    found = True
                    break
            if found:
                break
        if found:
            alive.add(culprit)
    return frozenset(alive)


@pytest.mark.parametrize(("n_people", "n_slots", "cases"), [(3, 3, 60), (2, 4, 80)])
def test_solver_matches_brute_force(n_people: int, n_slots: int, cases: int) -> None:
    rng = random.Random(20261030 + n_people)
    for _ in range(cases):
        view = _random_view(rng, n_people, n_slots)
        solver = Solver(view)
        everything = set(solver.all_statements())
        assert solver.consistent().consistent == _brute(view, everything), view
        assert solver.consistent(naive=True).consistent == _brute(view, everything, naive=True)
        subset = {i for i in everything if rng.random() < 0.5}
        assert solver.consistent(subset).consistent == _brute(view, subset)


def test_adding_statements_never_grows_the_consistent_set() -> None:
    rng = random.Random(7)
    for _ in range(60):
        view = _random_view(rng, 3, 3)
        solver = Solver(view)
        order = list(solver.all_statements())
        rng.shuffle(order)
        previous = solver.consistent(()).consistent
        for k in range(1, len(order) + 1):
            current = solver.consistent(order[:k]).consistent
            assert current <= previous
            previous = current


# --- Hand-made cases -----------------------------------------------------------------------------

P, Q = PersonId("p"), PersonId("q")


def _view(statements: Sequence[Statement], evidence: Sequence[Fact] = ()) -> PlayerView:
    return PlayerView(
        seed=0,
        world=_world([P, Q], 3),
        suspects=frozenset({P, Q}),
        motives=(),
        crime=CrimeReport(ITEM, C, SlotIndex(0), SlotIndex(2)),
        evidence=tuple(
            Evidence(EvidenceId(f"E{i}"), EvidenceKind.RECORD, (f,), _text("e"))
            for i, f in enumerate(evidence)
        ),
        testimony=tuple(
            Testimony(Query(QueryKind.WHERE, s.speaker, slot=SlotIndex(0)), (s,))
            for s in statements
        ),
    )


def _said(speaker: PersonId, fact: Fact) -> Statement:
    return Statement(speaker, fact, Basis.WITNESSED)


def test_no_information_leaves_everyone_consistent() -> None:
    assert solve(_view([])).consistent == {P, Q}


def test_witness_alibi_rules_out_a_suspect() -> None:
    # p says q was with p in room a during the only window slot: q cannot be the thief.
    view = _view([_said(P, Occupants(A, SlotIndex(1), frozenset({P, Q})))])
    assert solve(view).consistent == {P}


def test_window_conflict_points_at_one_of_the_two_speakers() -> None:
    # p claims to be alone in b; q claims p was not in b. Inside the window (T2) one must be lying.
    view = _view(
        [
            _said(P, Occupants(B, SlotIndex(1), frozenset({P}))),
            _said(Q, Occupants(B, SlotIndex(1), frozenset({Q}))),
        ]
    )
    assert solve(view).consistent == {P, Q}
    assert solve_trusting(view).consistent == {P, Q}
    assert solve_naive(view).consistent == frozenset()


def test_impossible_move_counts_as_a_conflict() -> None:
    # q at a in slot 0 and at c in slot 1 is impossible (a and c are not adjacent).
    view = _view([_said(Q, PersonAt(Q, C, SlotIndex(1)))], evidence=[PersonAt(Q, A, SlotIndex(0))])
    solver = Solver(view)
    assert solver.conflict_pairs() == ((0, EvidenceId("E0")),)
    assert solver.evidence_contradicts(0)


def test_outside_window_lie_exposed_by_evidence_is_ignored() -> None:
    # q's slot-0 claim is refuted by evidence, so under T3 it says nothing; q stays a suspect.
    view = _view([_said(Q, PersonAt(Q, A, SlotIndex(0)))], evidence=[PersonAt(Q, B, SlotIndex(0))])
    assert solve(view).consistent == {P, Q}


def test_item_sighting_moves_the_window() -> None:
    # Item seen at the scene in slot 1 (the whole window): nobody can have taken it in time.
    view = _view([_said(P, ItemAt(ITEM, C, SlotIndex(1)))])
    assert solve(view).consistent == {P}  # p's own claim does not bind p (T4), but binds q


def test_unknown_people_are_rejected() -> None:
    bad = _said(P, PersonAt(PersonId("ghost"), A, SlotIndex(0)))
    with pytest.raises(ValueError, match="unknown person"):
        Solver(_view([bad]))
