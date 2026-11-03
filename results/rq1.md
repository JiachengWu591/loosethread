# RQ1: solvability

Computed from `results/rows/` by `python -m loosethread.verify`.

```text
RQ1 deepseek-flash: 60 cases
  accepted: 50/60 = 83.3% [Wilson 95%: 72.0%, 90.7%]
  accepted, and the model's own truth holds: 50/60 = 83.3% [Wilson 95%: 72.0%, 90.7%]
  verdicts: accepted 50, invalid 2, multiple 1, too_easy 7
  invalid because: call:BackendUnavailable 1, too_long 1
  output tokens median 26273, max 64000; seconds median 156, max 354
  upper-bound spend: CNY 13.1668
RQ1 deepseek-flash: 204 cases
  accepted: 0/204 = 0.0% [Wilson 95%: 0.0%, 1.8%]
  accepted, and the model's own truth holds: 0/204 = 0.0% [Wilson 95%: 0.0%, 1.8%]
  verdicts: self_contradictory 204
  output tokens median 1022, max 1411; seconds median 4, max 6
  upper-bound spend: CNY 2.1315
Control: the generator's test cases through the same checker, which pass by construction and so check the checker: accepted 204
Comparison: the generator's attempts accepted, seeds 0-299: 300/2304 = 13.0% [Wilson 95%: 11.7%, 14.5%]
```
