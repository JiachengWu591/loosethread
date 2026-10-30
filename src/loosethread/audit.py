"""Truth-side audit of a generated case: checks the generator's guarantees against the ground truth.

Independent of the solver's reasoning: it evaluates facts directly on the true timeline. Returns a
list of problems (empty = all guarantees hold). Used by tests and by the batch report.
"""

from collections.abc import Mapping

from loosethread.model import (
    Basis,
    Case,
    Fact,
    ItemAt,
    LieReason,
    LocationId,
    Occupants,
    PersonAt,
    PersonId,
    Statement,
)
from loosethread.solver import Solver


def holds(
    fact: Fact, where: Mapping[tuple[PersonId, int], LocationId], items: Mapping[int, LocationId]
) -> bool:
    """Whether `fact` is true on the given timeline."""
    match fact:
        case PersonAt(person, location, slot):
            return where[(person, slot)] == location
        case Occupants(location, slot, people):
            present = {p for (p, t), loc in where.items() if t == slot and loc == location}
            return present == set(people)
        case ItemAt(_, location, slot):
            return items[slot] == location
    return False


def audit(case: Case) -> list[str]:
    view, truth = case.view, case.truth
    world = view.world
    problems: list[str] = []
    people = [p.id for p in world.people]
    n = len(world.slots)
    neighbors = {loc.id: loc.neighbors | {loc.id} for loc in world.locations}

    where = {(f.person, int(f.slot)): f.location for f in truth.timeline}
    if len(where) != len(truth.timeline) or set(where) != {
        (p, t) for p in people for t in range(n)
    }:
        problems.append("W1: timeline must give exactly one location per person and slot")
        return problems
    for p in people:
        for t in range(1, n):
            if where[(p, t)] not in neighbors[where[(p, t - 1)]]:
                problems.append(f"W2: {p} jumps between non-adjacent locations at slot {t}")
    items = {int(f.slot): f.location for f in truth.item_timeline}

    (theft,) = truth.events
    crime, window = view.crime, view.crime.window
    if theft.actor != truth.culprit or theft.slot not in window:
        problems.append("W4: theft must be by the culprit inside the window")
    if theft.location != crime.location or where[(truth.culprit, theft.slot)] != crime.location:
        problems.append("W4: the culprit must be at the crime scene at the theft slot")
    if any(where[(p, theft.slot)] == crime.location for p in people if p != truth.culprit):
        problems.append("W4: the culprit must be alone at the theft slot")
    for p in people:
        if p != truth.culprit and any(where[(p, t)] == crime.location for t in window):
            problems.append(f"uniqueness guard: innocent {p} visits the crime scene in the window")

    for e in view.evidence:
        if not all(holds(f, where, items) for f in e.establishes):
            problems.append(f"T1: evidence {e.id} is false")

    lie_cells = {(lie.statement.speaker, int(lie.statement.claim.slot)) for lie in truth.lies}
    for s in view.statements:
        if holds(s.claim, where, items):
            continue
        source = s.source if s.basis is Basis.HEARSAY else s.speaker
        if (source, int(s.claim.slot)) not in lie_cells:
            problems.append(f"unexplained false statement: {_short(s)}")

    evidence_people = {
        (f.person, int(f.slot)): f.location
        for e in view.evidence
        for f in e.establishes
        if isinstance(f, PersonAt)
    }
    for lie in truth.lies:
        speaker, slot = lie.statement.speaker, int(lie.statement.claim.slot)
        if lie.reason is LieReason.PRIVACY:
            if speaker == truth.culprit:
                problems.append("privacy lie attributed to the culprit")
            if slot in window:
                problems.append(f"T2: innocent {speaker} lies inside the window")
            if evidence_people.get((speaker, slot)) != where[(speaker, slot)]:
                problems.append(f"T3: innocent lie by {speaker} at slot {slot} lacks evidence")
        elif speaker != truth.culprit:
            problems.append("alibi lie attributed to an innocent")
    if not any(lie.reason is LieReason.ALIBI for lie in truth.lies):
        problems.append("T4: the culprit has no exposable alibi lie")

    if {m.person for m in view.motives} != set(view.suspects):
        problems.append("every suspect needs exactly one motive")
    result = Solver(view).consistent().consistent
    if result != {truth.culprit}:
        problems.append(f"solver: consistent suspects {sorted(result)} != culprit {truth.culprit}")
    return problems


def _short(s: Statement) -> str:
    return f"{s.speaker}: {s.claim}"
