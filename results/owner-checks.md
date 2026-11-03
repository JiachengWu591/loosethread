# The owner's checks

Computed from `results/rows/` by `python -m loosethread.verify`.

```text
Read by two Claude subagents, delegated by the owner (D-041), not by a person.
  the two runs give the same verdict: 85/85 = 100.0% [Wilson 95%: 95.7%, 100.0%]
  they are one model twice, so this does not show independent judges agree
Extractor, 30 test lines, right if both say so: 26/30 = 86.7% [Wilson 95%: 70.3%, 94.7%]
  fewer than 27 right, so the report carries the plan's caveat (STUDY_PLAN §8)
Judge sheet, arms A, B, C: 6 items, leaks if either says so: 0
Judge sheet, arm U: 19 items, leaks if either says so: 18
Flagged lines, read in a sample (post hoc): 30
  the item claim, flag stands: 6/6 = 100.0% [Wilson 95%: 61.0%, 100.0%]
  other failures, flag stands: 11/24 = 45.8% [Wilson 95%: 27.9%, 64.9%]
Line pairs: the owner's blind rating is not in yet.
```
