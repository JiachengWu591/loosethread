# Simulated players (P1, P2)

Computed from `results/rows/` by `python -m loosethread.verify`.

```text
The classic generator, budget 20 (CP-5):
4000 runs: 200 cases x 20 orders; rates are over cases
  questions to solve, per-case median run: median 12, p90 48, max 124
  first sweep (suspects x window): [15] questions; budget 20
  solved inside the first sweep (median run): 161/200 = 80.5% [Wilson 95%: 74.5%, 85.4%]
  median run within the budget: 166/200 = 83.0% [Wilson 95%: 77.2%, 87.6%]
  before CP-5: median run within ★★ (14): 160/200 = 80.0% [Wilson 95%: 73.9%, 85.0%]
  before CP-5: median run within ★★★ (minimum + 2): 0/200 = 0.0% [Wilson 95%: 0.0%, 1.9%]
  before CP-5: best of the orders within ★★★: 105/200 = 52.5% [Wilson 95%: 45.6%, 59.3%]
  some order identifies the culprit before an exposing pair is noted: 64/200 = 32.0% [Wilson 95%: 25.9%, 38.8%]
  runs (descriptive, correlated within cases): 339/4000 identify first, then need 3.1 more questions on average

The cases the game plays, budget 12:
6000 runs: 300 cases x 20 orders; rates are over cases
  questions to solve, per-case median run: median 10, p90 14, max 100
  first sweep (suspects x window): [15] questions; budget 12
  solved inside the first sweep (median run): 274/300 = 91.3% [Wilson 95%: 87.6%, 94.0%]
  median run within the budget: 239/300 = 79.7% [Wilson 95%: 74.8%, 83.8%]
  before CP-5: median run within ★★ (8): 67/300 = 22.3% [Wilson 95%: 18.0%, 27.4%]
  before CP-5: median run within ★★★ (minimum + 2): 0/300 = 0.0% [Wilson 95%: 0.0%, 1.3%]
  before CP-5: best of the orders within ★★★: 222/300 = 74.0% [Wilson 95%: 68.8%, 78.6%]
  some order identifies the culprit before an exposing pair is noted: 65/300 = 21.7% [Wilson 95%: 17.4%, 26.7%]
  runs (descriptive, correlated within cases): 307/6000 identify first, then need 5.2 more questions on average
  companion: 66 cases; oracle minimum median 3; questions to solve, median run: median 10, p90 12; within 12: 60/66 = 90.9% [Wilson 95%: 81.6%, 95.8%]
  evidence: 77 cases; oracle minimum median 1; questions to solve, median run: median 8, p90 10; within 12: 77/77 = 100.0% [Wilson 95%: 95.2%, 100.0%]
  occupied: 83 cases; oracle minimum median 3; questions to solve, median run: median 13, p90 63; within 12: 36/83 = 43.4% [Wilson 95%: 33.2%, 54.1%]
  unreachable: 74 cases; oracle minimum median 2; questions to solve, median run: median 10, p90 12; within 12: 66/74 = 89.2% [Wilson 95%: 80.1%, 94.4%]
  backstage: 100 cases; oracle minimum median 2; questions to solve, median run: median 10, p90 14; within 12: 71/100 = 71.0% [Wilson 95%: 61.5%, 79.0%]
  mistpine: 100 cases; oracle minimum median 3; questions to solve, median run: median 10, p90 13; within 12: 88/100 = 88.0% [Wilson 95%: 80.2%, 93.0%]
  night_ferry: 100 cases; oracle minimum median 2; questions to solve, median run: median 10, p90 33; within 12: 80/100 = 80.0% [Wilson 95%: 71.1%, 86.7%]
```
