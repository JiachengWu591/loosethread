# What a game costs with a model (P4)

Computed from `results/rows/` by `python -m loosethread.verify`.

```text
Scripted games: 20, on deepseek-flash at commit ff1300e
  each is everyone over the theft window until the budget ends, plus one repeat and one bit of small talk
CNY per game, upper bound: median 0.077, p95 0.079, most 0.079
Questions charged per game: median 12, p95 12, most 12
Model calls per game: median 28, p95 28, most 28
Seconds per turn in the model: median 2.2, p95 3.8, most 16.9
Lines the template replaced: 0/280 = 0.0% [Wilson 95%: 0.0%, 1.4%]
Turns that could not reach the model: 0/280 = 0.0% [Wilson 95%: 0.0%, 1.4%]
P4 model spending so far, upper bound: CNY 2.18 of 5.00
These are scripted questions, in a loop no player would write. The owner's own game is not in these rows.
```
