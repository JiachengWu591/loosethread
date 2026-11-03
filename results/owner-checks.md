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
Line pairs, rated blind by the owner, one rater: 30 pairs, 0 ties
  B sounds more like a person: 10/30 = 33.3% [Wilson 95%: 19.2%, 51.2%]
  A 20, B 10; exact sign test p = 0.0987
  en: A 10, B 5
  zh: A 10, B 5
  A's line carries a failure flag, post hoc: 1 of the 20 A won
```
