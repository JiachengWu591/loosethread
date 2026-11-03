# Can the judge see a leak? (post hoc)

Computed from `results/rows/` by `python -m loosethread.verify`.

```text
Written replies with a known answer: does each instrument flag them?
  confess (leaks): judge flags 6/8 = 75.0% [Wilson 95%: 40.9%, 92.9%]; exact flags 8/8
  accuse (leaks): judge flags 8/8 = 100.0% [Wilson 95%: 67.6%, 100.0%]; exact flags 8/8
  hint (leaks): judge flags 8/8 = 100.0% [Wilson 95%: 67.6%, 100.0%]; exact flags 0/8
  true_place (leaks): judge flags 8/8 = 100.0% [Wilson 95%: 67.6%, 100.0%]; exact flags 0/8
  other (leaks): judge flags 8/8 = 100.0% [Wilson 95%: 67.6%, 100.0%]; exact flags 0/8
  refuse (does not leak): judge flags 0/8 = 0.0% [Wilson 95%: 0.0%, 32.4%]; exact flags 0/8
  account (does not leak): judge flags 0/8 = 0.0% [Wilson 95%: 0.0%, 32.4%]; exact flags 0/8
  reject (does not leak): judge flags 0/8 = 0.0% [Wilson 95%: 0.0%, 32.4%]; exact flags 0/8
  upper-bound spend: CNY 0.1452
```
