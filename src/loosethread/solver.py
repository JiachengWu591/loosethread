"""Independent case solver. It reads only the player's view, never truth fields or generator code.

Semantics (DESIGN.md §3, §4, §10). Hypothesis "c is the culprit" is consistent iff some timeline
satisfies the world rules W1–W4 with c as the thief, makes every evidence fact true, and makes true
every statement whose (effective) speaker is not c and that either concerns a theft-window slot (T2)
or is not contradicted by evidence (T3). Hearsay counts as a claim by its source (T5).

Every constraint is either unary — "person p is / is not at location L in slot t" — or links one
person's consecutive slots (W2). For a fixed theft slot the persons are therefore independent, and
each person's feasibility is a reachability check over a bitmask DP. The check is exact.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import assert_never

from loosethread.model import (
    Basis,
    EvidenceId,
    Fact,
    ItemAt,
    LocationId,
    Occupants,
    PersonAt,
    PersonId,
    PlayerView,
    Statement,
)

# (person index, slot, allowed-location bitmask)
type Constraint = tuple[int, int, int]
type Domains = list[list[int]]


@dataclass(frozen=True)
class SolveResult:
    consistent: frozenset[PersonId]

    @property
    def unique(self) -> PersonId | None:
        return next(iter(self.consistent)) if len(self.consistent) == 1 else None


@dataclass(frozen=True)
class _Compiled:
    constraints: tuple[Constraint, ...]
    speaker: int  # effective speaker (the source, for hearsay)
    in_window: bool
    evidence_contradicted: bool
    item_bound: int  # theft slot must be later than this (-1: no bound)


class Solver:
    """Compiled form of one `PlayerView`. Statements are addressed by index into `statements`."""

    def __init__(self, view: PlayerView) -> None:
        world = view.world
        self.view = view
        self.people: tuple[PersonId, ...] = tuple(p.id for p in world.people)
        self._pidx = {pid: i for i, pid in enumerate(self.people)}
        self._lidx = {loc.id: i for i, loc in enumerate(world.locations)}
        self._all = (1 << len(world.locations)) - 1
        self._n_slots = len(world.slots)
        closed = [
            (1 << i) | sum(1 << self._lidx[n] for n in loc.neighbors)
            for i, loc in enumerate(world.locations)
        ]
        self._expand = _expand_table(closed)
        self._crime_bit = 1 << self._lidx[view.crime.location]
        self._window = tuple(int(t) for t in view.crime.window)
        self.suspects: tuple[PersonId, ...] = tuple(p for p in self.people if p in view.suspects)

        self._evidence_items: tuple[tuple[EvidenceId, tuple[Constraint, ...]], ...] = tuple(
            (e.id, tuple(c for f in e.establishes for c in self._constraints(f, None)))
            for e in view.evidence
        )
        self._evidence_bound = max(
            (self._item_bound(f) for e in view.evidence for f in e.establishes), default=-1
        )
        evidence_domains = self._fresh()
        for _, cons in self._evidence_items:
            _apply(evidence_domains, cons)
        self._evidence_domains = evidence_domains

        self.statements: tuple[Statement, ...] = view.statements
        self._compiled = tuple(self._compile(s) for s in self.statements)

    # --- Compilation ---------------------------------------------------------------------------

    def _person(self, pid: PersonId) -> int:
        try:
            return self._pidx[pid]
        except KeyError:
            raise ValueError(f"unknown person {pid!r}") from None

    def _bit(self, loc: LocationId) -> int:
        try:
            return 1 << self._lidx[loc]
        except KeyError:
            raise ValueError(f"unknown location {loc!r}") from None

    def _slot(self, slot: int) -> int:
        if not 0 <= slot < self._n_slots:
            raise ValueError(f"slot {slot} is outside the evening")
        return slot

    def _constraints(self, fact: Fact, witness: PersonId | None) -> tuple[Constraint, ...]:
        match fact:
            case PersonAt(person, location, slot):
                return ((self._person(person), self._slot(slot), self._bit(location)),)
            case Occupants(location, slot, people):
                bit, t = self._bit(location), self._slot(slot)
                present = {self._person(p) for p in people}
                return tuple(
                    (i, t, bit if i in present else self._all & ~bit)
                    for i in range(len(self.people))
                )
            case ItemAt(_, location, slot):
                # A witnessed sighting places the witness there; the item itself is unconstrained.
                if witness is None:
                    return ()
                return ((self._person(witness), self._slot(slot), self._bit(location)),)
            case _:
                assert_never(fact)

    def _item_bound(self, fact: Fact) -> int:
        crime = self.view.crime
        if isinstance(fact, ItemAt) and fact.item == crime.item and fact.location == crime.location:
            return int(fact.slot)
        return -1

    def _compile(self, statement: Statement) -> _Compiled:
        source = statement.source if statement.basis is Basis.HEARSAY else statement.speaker
        assert source is not None  # guaranteed by Statement validation
        constraints = self._constraints(statement.claim, source)
        return _Compiled(
            constraints=constraints,
            speaker=self._person(source),
            in_window=int(statement.claim.slot) in self._window,
            evidence_contradicted=self._contradicted_by_evidence(constraints),
            item_bound=self._item_bound(statement.claim),
        )

    def _contradicted_by_evidence(self, constraints: Iterable[Constraint]) -> bool:
        """Direct conflict with evidence: same slot (W1) or an impossible move to/from it (W2)."""
        domains, expand, last = self._evidence_domains, self._expand, self._n_slots - 1
        for (p, t), mask in _cell_masks(constraints).items():
            if not domains[p][t] & mask:
                return True
            if t > 0 and not expand[domains[p][t - 1]] & mask:
                return True
            if t < last and not expand[domains[p][t + 1]] & mask:
                return True
        return False

    # --- Core check ------------------------------------------------------------------------------

    def _fresh(self) -> Domains:
        return [[self._all] * self._n_slots for _ in self.people]

    def _must_hold(self, s: _Compiled, culprit: int, naive: bool) -> bool:
        if naive:
            return not s.evidence_contradicted
        return s.speaker != culprit and (s.in_window or not s.evidence_contradicted)

    def _domains(
        self, culprit: int, active: Iterable[int], naive: bool = False
    ) -> tuple[Domains, int] | None:
        """Domains and theft-slot lower bound under the hypothesis, or None if already empty."""
        domains = [row[:] for row in self._evidence_domains]
        bound = self._evidence_bound
        for index in active:
            s = self._compiled[index]
            if not self._must_hold(s, culprit, naive):
                continue
            if not _apply(domains, s.constraints):
                return None
            bound = max(bound, s.item_bound)
        return domains, bound

    def _path_ok(self, row: Sequence[int], slot: int = -1, mask: int = 0) -> bool:
        expand = self._expand
        reach = row[0] & mask if slot == 0 else row[0]
        for t in range(1, len(row)):
            if not reach:
                return False
            reach = expand[reach] & (row[t] & mask if t == slot else row[t])
        return bool(reach)

    def _theft_slots(self, culprit: int, domains: Domains, bound: int) -> int:
        """Number of theft slots for which the hypothesis has a consistent timeline."""
        if not all(self._path_ok(row) for row in domains):
            return 0
        not_crime = self._all & ~self._crime_bit
        count = 0
        for theta in self._window:
            if theta <= bound:
                continue
            if self._path_ok(domains[culprit], theta, self._crime_bit) and all(
                self._path_ok(row, theta, not_crime)
                for i, row in enumerate(domains)
                if i != culprit
            ):
                count += 1
        return count

    # --- Public API ----------------------------------------------------------------------------

    def all_statements(self) -> range:
        return range(len(self.statements))

    def hypothesis_ok(
        self, suspect: PersonId, active: Iterable[int] | None = None, naive: bool = False
    ) -> bool:
        culprit = self._person(suspect)
        state = self._domains(culprit, self.all_statements() if active is None else active, naive)
        return state is not None and self._theft_slots(culprit, *state) > 0

    def consistent(self, active: Iterable[int] | None = None, naive: bool = False) -> SolveResult:
        chosen = tuple(self.all_statements() if active is None else active)
        return SolveResult(
            frozenset(s for s in self.suspects if self.hypothesis_ok(s, chosen, naive))
        )

    def profile(self, active: Iterable[int]) -> tuple[frozenset[PersonId], int]:
        """Consistent suspects and the total number of feasible (suspect, theft slot) pairs."""
        chosen = tuple(active)
        alive: set[PersonId] = set()
        pairs = 0
        for suspect in self.suspects:
            culprit = self._person(suspect)
            state = self._domains(culprit, chosen)
            n = 0 if state is None else self._theft_slots(culprit, *state)
            if n:
                alive.add(suspect)
                pairs += n
        return frozenset(alive), pairs

    def evidence_contradicts(self, index: int) -> bool:
        return self._compiled[index].evidence_contradicted

    def conflict_pairs(self) -> tuple[tuple[int, int | EvidenceId], ...]:
        """Pairs of directly conflicting items (statement-statement or statement-evidence).

        Two items conflict when, for one person, they allow no common location in the same slot
        (W1), or no possible move between consecutive slots (W2). Statement pairs are (i, j) with
        i < j; evidence pairs are (i, evidence id). Evidence-evidence pairs cannot occur in a valid
        case and are not reported.
        """
        items: list[int | EvidenceId] = [
            *self.all_statements(),
            *(e for e, _ in self._evidence_items),
        ]
        all_constraints = [
            *(s.constraints for s in self._compiled),
            *(cons for _, cons in self._evidence_items),
        ]
        cells: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for pos, cons in enumerate(all_constraints):
            for key, mask in _cell_masks(cons).items():
                cells.setdefault(key, []).append((pos, mask))
        found: set[tuple[int, int | EvidenceId]] = set()

        def note(a: int, b: int) -> None:
            item_a, item_b = items[a], items[b]
            if isinstance(item_a, int) and isinstance(item_b, int):
                found.add((min(item_a, item_b), max(item_a, item_b)))
            elif isinstance(item_a, int):
                found.add((item_a, item_b))
            elif isinstance(item_b, int):
                found.add((item_b, item_a))

        for (person, slot), entries in cells.items():
            for x in range(len(entries)):
                pos_a, mask_a = entries[x]
                for pos_b, mask_b in entries[x + 1 :]:
                    if not mask_a & mask_b:
                        note(pos_a, pos_b)
                reach = self._expand[mask_a]
                for pos_b, mask_b in cells.get((person, slot + 1), ()):
                    if pos_b != pos_a and not reach & mask_b:
                        note(pos_a, pos_b)
        return tuple(sorted(found, key=lambda p: (p[0], str(p[1]))))

    def contested(self) -> frozenset[int]:
        """Statements involved in at least one direct conflict."""
        involved: set[int] = set()
        for a, b in self.conflict_pairs():
            involved.add(a)
            if isinstance(b, int):
                involved.add(b)
        return frozenset(involved)


def solve(view: PlayerView) -> SolveResult:
    """Full rules over every statement."""
    return Solver(view).consistent()


def solve_naive(view: PlayerView) -> SolveResult:
    """DESIGN §10 naive reading: believe every statement that evidence does not contradict."""
    return Solver(view).consistent(naive=True)


def solve_trusting(view: PlayerView) -> SolveResult:
    """Full rules over the uncontested statements only (no contradiction resolved)."""
    solver = Solver(view)
    contested = solver.contested()
    return solver.consistent(i for i in solver.all_statements() if i not in contested)


# --- Helpers -----------------------------------------------------------------------------------


def _expand_table(closed: Sequence[int]) -> tuple[int, ...]:
    """expand[mask] = locations reachable in one step (stay or move) from any location in mask."""
    table = [0] * (1 << len(closed))
    for mask in range(1, len(table)):
        low = mask & -mask
        table[mask] = table[mask ^ low] | closed[low.bit_length() - 1]
    return tuple(table)


def _apply(domains: Domains, constraints: Iterable[Constraint]) -> bool:
    """Narrow domains in place; returns False once any cell becomes empty (it stays empty)."""
    ok = True
    for person, slot, mask in constraints:
        domains[person][slot] &= mask
        ok = ok and bool(domains[person][slot])
    return ok


def _cell_masks(constraints: Iterable[Constraint]) -> dict[tuple[int, int], int]:
    masks: dict[tuple[int, int], int] = {}
    for person, slot, mask in constraints:
        key = (person, slot)
        masks[key] = masks.get(key, -1) & mask
    return masks
