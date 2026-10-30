"""Difficulty metrics, computed from the player view only (through the solver).

- contradictions_required: the fewest conflict groups whose statements must be taken into account
  (under the full rules) before the culprit is unique. Uncontested statements are always used.
- min_questions: questions needed for a unique solution. Exact when it is 0, 1 or 2 (all single
  questions are checked, then both sides of every conflict); otherwise a greedy-then-pruned upper
  bound with a known lower bound of 2.
- inference_steps: for each innocent suspect, the size of an irreducible set of statements that
  still rules them out (deletion-based, so irreducible but not necessarily minimum), summed.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations

from loosethread.model import PlayerView, Query
from loosethread.solver import Solver

MAX_GROUPS_SEARCHED = 3


@dataclass(frozen=True)
class Metrics:
    conflict_pairs: int
    contested_statements: int
    naive_suspects: int  # consistent under the DESIGN §10 naive reading
    trusting_suspects: int  # consistent using only uncontested statements
    contradictions_required: int | None  # None: more than MAX_GROUPS_SEARCHED
    min_questions: int
    min_questions_exact: bool
    question_plan: tuple[Query, ...]  # a plan of `min_questions` questions that solves the case
    inference_steps: int


def measure(view: PlayerView, solver: Solver | None = None) -> Metrics:
    solver = solver or Solver(view)
    contested = solver.contested()
    uncontested = [i for i in solver.all_statements() if i not in contested]
    question_plan, exact = _min_questions(view, solver)
    return Metrics(
        conflict_pairs=len(solver.conflict_pairs()),
        contested_statements=len(contested),
        naive_suspects=len(solver.consistent(naive=True).consistent),
        trusting_suspects=len(solver.consistent(uncontested).consistent),
        contradictions_required=_contradictions_required(solver, uncontested),
        min_questions=len(question_plan),
        min_questions_exact=exact,
        question_plan=question_plan,
        inference_steps=_inference_steps(solver),
    )


def _conflict_groups(solver: Solver) -> list[frozenset[int]]:
    """Connected groups of contested statements (statements sharing evidence are connected)."""
    parent: dict[object, object] = {}

    def find(x: object) -> object:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in solver.conflict_pairs():
        parent[find(a)] = find(("e", b) if not isinstance(b, int) else b)
    groups: dict[object, set[int]] = {}
    for node in list(parent):
        if isinstance(node, int):
            groups.setdefault(find(node), set()).add(node)
    return sorted((frozenset(g) for g in groups.values()), key=min)


def _contradictions_required(solver: Solver, uncontested: list[int]) -> int | None:
    groups = _conflict_groups(solver)
    for k in range(min(MAX_GROUPS_SEARCHED, len(groups)) + 1):
        for chosen in combinations(groups, k):
            active = uncontested + [i for g in chosen for i in g]
            if solver.consistent(active).unique is not None:
                return k
    return None


def _min_questions(view: PlayerView, solver: Solver) -> tuple[tuple[Query, ...], bool]:
    """A short question plan that makes the culprit unique, and whether it is provably minimal."""
    index = {s: i for i, s in enumerate(solver.statements)}
    asked: dict[frozenset[int], Query] = {}
    for t in view.testimony:
        asked.setdefault(frozenset(index[c] for c in t.claims), t.query)
    candidates = list(asked)

    def unique(active: Iterable[int]) -> bool:
        return len(solver.profile(active)[0]) == 1

    def plan(*answers: frozenset[int]) -> tuple[Query, ...]:
        return tuple(asked[a] for a in answers)

    if unique(()):
        return (), True
    for cand in candidates:
        if unique(cand):
            return plan(cand), True
    # Two questions: the usual solution asks both sides of one conflict. Checking those pairs is
    # cheap; any hit is exact because no single question suffices.
    containing: dict[int, list[frozenset[int]]] = {}
    for cand in candidates:
        for i in cand:
            containing.setdefault(i, []).append(cand)
    for a, b in solver.conflict_pairs():
        if not isinstance(b, int):
            continue
        for ca in containing.get(a, [])[:3]:
            for cb in containing.get(b, [])[:3]:
                if unique(ca | cb):
                    return plan(ca, cb), True

    chosen: list[frozenset[int]] = []
    active: set[int] = set()
    while not unique(active):
        best: tuple[tuple[int, int, int, int], frozenset[int]] | None = None
        for order, cand in enumerate(candidates):
            new = cand - active
            if not new:
                continue
            alive, pairs = solver.profile(active | cand)
            key = (len(alive), pairs, -len(new), order)
            if best is None or key < best[0]:
                best = (key, cand)
        if best is None:
            break
        chosen.append(best[1])
        active |= best[1]
    for cand in reversed(list(chosen)):
        rest = [c for c in chosen if c is not cand]
        if unique(i for c in rest for i in c):
            chosen = rest
    # No single question suffices, so a pruned greedy result of 2 is exact; above 2 it is an upper
    # bound (pairs outside conflict pairs were not searched).
    return plan(*chosen), len(chosen) <= 2


def _inference_steps(solver: Solver) -> int:
    total = 0
    everything = list(solver.all_statements())
    for suspect in solver.suspects:
        if solver.hypothesis_ok(suspect, everything):
            continue
        needed = list(everything)
        for i in reversed(everything):
            trial = [j for j in needed if j != i]
            if not solver.hypothesis_ok(suspect, trial):
                needed = trial
        total += len(needed)
    return total
