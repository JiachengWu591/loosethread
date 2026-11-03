# RQ3: static attacks

Computed from `results/rows/` by `python -m loosethread.verify`.

```text
RQ3 arm A: 200 attacks, 3 retried after a failed call
  leak, failing closed: 3/200 = 1.5% [Wilson 95%: 0.5%, 4.3%]
  leak or no usable reply, against the arm: 4/200 = 2.0% [Wilson 95%: 0.8%, 5.0%]
  leak, goal in reach (secondary): 3/178 = 1.7% [Wilson 95%: 0.6%, 4.8%]
  no usable reply: 1/200 = 0.5% [Wilson 95%: 0.1%, 2.8%]
  exact matching and judge disagree: 3, judgement unreadable: 0, decided by the owner: 0
  accuses anyone: 0/200 = 0.0% [Wilson 95%: 0.0%, 1.9%]
  accuses the culprit (chance is 1 in 5 of the above): 0
  reveals instructions, separate: 0/200 = 0.0% [Wilson 95%: 0.0%, 1.9%]
    direct: 0/40 = 0.0% [Wilson 95%: 0.0%, 8.8%]
    encoding: 0/40 = 0.0% [Wilson 95%: 0.0%, 8.8%]
    forged: 1/40 = 2.5% [Wilson 95%: 0.4%, 12.9%]
    override: 1/40 = 2.5% [Wilson 95%: 0.4%, 12.9%]
    roleplay: 1/40 = 2.5% [Wilson 95%: 0.4%, 12.9%]
  upper-bound spend: CNY 1.4466
RQ3 arm B: 200 attacks, 2 retried after a failed call
  leak, failing closed: 1/200 = 0.5% [Wilson 95%: 0.1%, 2.8%]
  leak or no usable reply, against the arm: 2/200 = 1.0% [Wilson 95%: 0.3%, 3.6%]
  leak, goal in reach (secondary): 1/178 = 0.6% [Wilson 95%: 0.1%, 3.1%]
  no usable reply: 1/200 = 0.5% [Wilson 95%: 0.1%, 2.8%]
  exact matching and judge disagree: 0, judgement unreadable: 1, decided by the owner: 0
  accuses anyone: 0/200 = 0.0% [Wilson 95%: 0.0%, 1.9%]
  accuses the culprit (chance is 1 in 5 of the above): 0
  reveals instructions, separate: 0/200 = 0.0% [Wilson 95%: 0.0%, 1.9%]
  attacks that burn a charged question: 23/200 = 11.5% [Wilson 95%: 7.8%, 16.7%]
    direct: 0/40 = 0.0% [Wilson 95%: 0.0%, 8.8%]
    encoding: 0/40 = 0.0% [Wilson 95%: 0.0%, 8.8%]
    forged: 1/40 = 2.5% [Wilson 95%: 0.4%, 12.9%]
    override: 0/40 = 0.0% [Wilson 95%: 0.0%, 8.8%]
    roleplay: 0/40 = 0.0% [Wilson 95%: 0.0%, 8.8%]
  upper-bound spend: CNY 1.5092
RQ3 arm C: 200 attacks, 3 retried after a failed call
  leak, failing closed: 2/200 = 1.0% [Wilson 95%: 0.3%, 3.6%]
  leak or no usable reply, against the arm: 3/200 = 1.5% [Wilson 95%: 0.5%, 4.3%]
  leak, goal in reach (secondary): 2/178 = 1.1% [Wilson 95%: 0.3%, 4.0%]
  no usable reply: 1/200 = 0.5% [Wilson 95%: 0.1%, 2.8%]
  exact matching and judge disagree: 2, judgement unreadable: 0, decided by the owner: 0
  accuses anyone: 0/200 = 0.0% [Wilson 95%: 0.0%, 1.9%]
  accuses the culprit (chance is 1 in 5 of the above): 0
  reveals instructions, separate: 0/200 = 0.0% [Wilson 95%: 0.0%, 1.9%]
    direct: 0/40 = 0.0% [Wilson 95%: 0.0%, 8.8%]
    encoding: 0/40 = 0.0% [Wilson 95%: 0.0%, 8.8%]
    forged: 0/40 = 0.0% [Wilson 95%: 0.0%, 8.8%]
    override: 1/40 = 2.5% [Wilson 95%: 0.4%, 12.9%]
    roleplay: 1/40 = 2.5% [Wilson 95%: 0.4%, 12.9%]
  upper-bound spend: CNY 1.0562
  attacks that leak, B vs A: only B 1, only A 3 of 200 pairs; exact McNemar p = 0.625
  attacks that leak, C vs A: only C 0, only A 1 of 200 pairs; exact McNemar p = 1
  attacks that leak, B vs C: only B 1, only C 2 of 200 pairs; exact McNemar p = 1
  attacks that leak, goal in reach (secondary), B vs A: only B 1, only A 3 of 178 pairs; exact McNemar p = 0.625
  attacks that leak, goal in reach (secondary), C vs A: only C 0, only A 1 of 178 pairs; exact McNemar p = 1
  attacks that leak, goal in reach (secondary), B vs C: only B 1, only C 2 of 178 pairs; exact McNemar p = 1
```
