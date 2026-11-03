# Run-to-run stability

Computed from `results/rows/` by `python -m loosethread.verify`.

```text
Repeat arm A: 20 turns asked twice, each the speaker's first
  same line, word for word: 11/20 = 55.0% [Wilson 95%: 34.2%, 74.2%]
  same extracted claims: 18/20 = 90.0% [Wilson 95%: 69.9%, 97.2%]
  same failures: 20/20 = 100.0% [Wilson 95%: 83.9%, 100.0%]
  same answer or not: 20/20 = 100.0% [Wilson 95%: 83.9%, 100.0%]
  no usable reading in one run or both: 0
  upper-bound spend: CNY 0.1475
Repeat arm B: 20 turns asked twice, each the speaker's first
  same line, word for word: 18/20 = 90.0% [Wilson 95%: 69.9%, 97.2%]
  same extracted claims: 19/20 = 95.0% [Wilson 95%: 76.4%, 99.1%]
  same failures: 19/20 = 95.0% [Wilson 95%: 76.4%, 99.1%]
  same answer or not: 19/20 = 95.0% [Wilson 95%: 76.4%, 99.1%]
  no usable reading in one run or both: 1
  upper-bound spend: CNY 0.1550
Repeat arm C: 20 turns asked twice, each the speaker's first
  same line, word for word: 12/20 = 60.0% [Wilson 95%: 38.7%, 78.1%]
  same extracted claims: 16/20 = 80.0% [Wilson 95%: 58.4%, 91.9%]
  same failures: 18/20 = 90.0% [Wilson 95%: 69.9%, 97.2%]
  same answer or not: 18/20 = 90.0% [Wilson 95%: 69.9%, 97.2%]
  no usable reading in one run or both: 1
  upper-bound spend: CNY 0.1039
```
