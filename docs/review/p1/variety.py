"""Variety of generated cases (P1 review, CP-4): theft slot, culprit, alibi room, exposure.

uv run python docs/review/p1/variety.py   # seeds 0-999, default parameters
"""

from collections import Counter

from loosethread.generator import generate
from loosethread.lookup import AnswerBook
from loosethread.model import LieReason, PersonAt
from loosethread.stats import wilson

N = 1000


def show(name: str, counter: Counter[str]) -> None:
    print(f"{name}:")
    for key, count in sorted(counter.items(), key=lambda kv: -kv[1]):
        lo, hi = wilson(count, N)
        print(f"  {key:<14} {count:>4} = {count / N:5.1%}  [Wilson 95%: {lo:.1%}, {hi:.1%}]")


position: Counter[str] = Counter()
theft_slot: Counter[str] = Counter()
culprit: Counter[str] = Counter()
alibi_room: Counter[str] = Counter()
exposers: Counter[str] = Counter()
privacy: Counter[str] = Counter()
for seed in range(N):
    case = generate(seed).case
    view, truth = case.view, case.truth
    (theft,) = truth.events
    window = list(view.crime.window)
    position[f"{window.index(theft.slot) + 1} of {len(window)}"] += 1
    theft_slot[view.world.slots[int(theft.slot)].label] += 1
    culprit[str(truth.culprit)] += 1
    book = AnswerBook.from_truth(view.world, truth)
    for lie in truth.lies:
        claim = lie.statement.claim
        assert isinstance(claim, PersonAt)
        if lie.reason is LieReason.ALIBI:
            alibi_room[str(book.claimed_location(lie.statement.speaker, int(claim.slot)))] += 1
            exposers[f"{len(lie.exposed_by)} item(s)"] += 1
    privacy[str(sum(lie.reason is LieReason.PRIVACY for lie in truth.lies))] += 1

show("theft slot position in the window", position)
show("theft slot", theft_slot)
show("culprit", culprit)
show("room claimed in the alibi lie", alibi_room)
show("alibi lie exposed by", exposers)
show("privacy lies per case", privacy)
