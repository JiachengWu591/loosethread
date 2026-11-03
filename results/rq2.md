# RQ2: consistency, and the cost of valid answers

Computed from `results/rows/` by `python -m loosethread.verify`.

```text
RQ2 arm A: 204 sessions, unit = case
  sessions with an integrity failure: 60/204 = 29.4% [Wilson 95%: 23.6%, 36.0%]
  counting unusable replies against the arm: 61/204 = 29.9% [Wilson 95%: 24.0%, 36.5%]
    lie_broken: 0/204 = 0.0% [Wilson 95%: 0.0%, 1.8%]
    unauthorized_true: 1/204 = 0.5% [Wilson 95%: 0.1%, 2.7%]
    fabricated: 60/204 = 29.4% [Wilson 95%: 23.6%, 36.0%]
    contradiction: 7/204 = 3.4% [Wilson 95%: 1.7%, 6.9%]
  valid answers, turns 1-6, descriptive: 1178/1224 = 96.2% [Wilson 95%: 95.0%, 97.2%]
  tokens per session: median 18966, p95 19804
  seconds per session: median 9.1, p95 10.3
  upper-bound CNY per session: median 0.0588, p95 0.0607
  upper-bound spend: CNY 11.9816
RQ2 arm B: 204 sessions, unit = case
  sessions with an integrity failure: 0/204 = 0.0% [Wilson 95%: 0.0%, 1.8%]
  counting unusable replies against the arm: 0/204 = 0.0% [Wilson 95%: 0.0%, 1.8%]
    lie_broken: 0/204 = 0.0% [Wilson 95%: 0.0%, 1.8%]
    unauthorized_true: 0/204 = 0.0% [Wilson 95%: 0.0%, 1.8%]
    fabricated: 0/204 = 0.0% [Wilson 95%: 0.0%, 1.8%]
    contradiction: 0/204 = 0.0% [Wilson 95%: 0.0%, 1.8%]
  valid answers, turns 1-6, descriptive: 1224/1224 = 100.0% [Wilson 95%: 99.7%, 100.0%]
  tokens per session: median 21272, p95 21544
  seconds per session: median 17.1, p95 18.7
  upper-bound CNY per session: median 0.0630, p95 0.0642
  upper-bound spend: CNY 12.8170
RQ2 arm C: 204 sessions, unit = case
  sessions with an integrity failure: 76/204 = 37.3% [Wilson 95%: 30.9%, 44.1%]
  counting unusable replies against the arm: 77/204 = 37.7% [Wilson 95%: 31.4%, 44.6%]
    lie_broken: 0/204 = 0.0% [Wilson 95%: 0.0%, 1.8%]
    unauthorized_true: 1/204 = 0.5% [Wilson 95%: 0.1%, 2.7%]
    fabricated: 76/204 = 37.3% [Wilson 95%: 30.9%, 44.1%]
    contradiction: 8/204 = 3.9% [Wilson 95%: 2.0%, 7.5%]
  valid answers, turns 1-6, descriptive: 1158/1224 = 94.6% [Wilson 95%: 93.2%, 95.7%]
  tokens per session: median 11202, p95 11517
  seconds per session: median 9.0, p95 10.1
  upper-bound CNY per session: median 0.0430, p95 0.0449
  upper-bound spend: CNY 8.7832
  sessions with a failure, B vs A: only B 0, only A 60 of 204 pairs; exact McNemar p = 1.73e-18
  sessions with a failure, C vs A: only C 29, only A 13 of 204 pairs; exact McNemar p = 0.0195
  sessions with a failure, B vs C: only B 0, only C 76 of 204 pairs; exact McNemar p = 2.65e-23
RQ2, sessions with an integrity failure, by group (secondary)
  en, arm A: 13/102 = 12.7% [Wilson 95%: 7.6%, 20.6%]
  en, arm B: 0/102 = 0.0% [Wilson 95%: 0.0%, 3.6%]
  en, arm C: 14/102 = 13.7% [Wilson 95%: 8.4%, 21.7%]
  zh, arm A: 47/102 = 46.1% [Wilson 95%: 36.7%, 55.7%]
  zh, arm B: 0/102 = 0.0% [Wilson 95%: 0.0%, 3.6%]
  zh, arm C: 62/102 = 60.8% [Wilson 95%: 51.1%, 69.7%]
  backstage, arm A: 23/68 = 33.8% [Wilson 95%: 23.7%, 45.7%]
  backstage, arm B: 0/68 = 0.0% [Wilson 95%: 0.0%, 5.3%]
  backstage, arm C: 27/68 = 39.7% [Wilson 95%: 28.9%, 51.6%]
  mistpine, arm A: 26/68 = 38.2% [Wilson 95%: 27.6%, 50.1%]
  mistpine, arm B: 0/68 = 0.0% [Wilson 95%: 0.0%, 5.3%]
  mistpine, arm C: 33/68 = 48.5% [Wilson 95%: 37.1%, 60.2%]
  night_ferry, arm A: 11/68 = 16.2% [Wilson 95%: 9.3%, 26.7%]
  night_ferry, arm B: 0/68 = 0.0% [Wilson 95%: 0.0%, 5.3%]
  night_ferry, arm C: 16/68 = 23.5% [Wilson 95%: 15.0%, 34.9%]
  companion, arm A: 12/51 = 23.5% [Wilson 95%: 14.0%, 36.8%]
  companion, arm B: 0/51 = 0.0% [Wilson 95%: 0.0%, 7.0%]
  companion, arm C: 15/51 = 29.4% [Wilson 95%: 18.7%, 43.0%]
  evidence, arm A: 18/51 = 35.3% [Wilson 95%: 23.6%, 49.0%]
  evidence, arm B: 0/51 = 0.0% [Wilson 95%: 0.0%, 7.0%]
  evidence, arm C: 21/51 = 41.2% [Wilson 95%: 28.8%, 54.8%]
  occupied, arm A: 13/51 = 25.5% [Wilson 95%: 15.5%, 38.9%]
  occupied, arm B: 0/51 = 0.0% [Wilson 95%: 0.0%, 7.0%]
  occupied, arm C: 20/51 = 39.2% [Wilson 95%: 27.0%, 52.9%]
  unreachable, arm A: 17/51 = 33.3% [Wilson 95%: 22.0%, 47.0%]
  unreachable, arm B: 0/51 = 0.0% [Wilson 95%: 0.0%, 7.0%]
  unreachable, arm C: 20/51 = 39.2% [Wilson 95%: 27.0%, 52.9%]
RQ2, the lines themselves (descriptive)
  arm A, en: median line length 18
  arm A, zh: median line length 25
  arm A: sentences that repeat one in the session: 26/2317 = 1.1% [Wilson 95%: 0.8%, 1.6%]
  arm B, en: median line length 13
  arm B, zh: median line length 29
  arm B: sentences that repeat one in the session: 377/2128 = 17.7% [Wilson 95%: 16.2%, 19.4%]
  arm B: lines replaced by the template: 0/1632 = 0.0% [Wilson 95%: 0.0%, 0.2%]
  arm C, en: median line length 18
  arm C, zh: median line length 24
  arm C: sentences that repeat one in the session: 32/2255 = 1.4% [Wilson 95%: 1.0%, 2.0%]
RQ2, post hoc, not in the plan
  arm A, a failure other than claiming to have seen the item: 26/204 = 12.7% [Wilson 95%: 8.8%, 18.0%]
    en: other failures 9/102 = 8.8% [Wilson 95%: 4.7%, 15.9%]; the item claim 5/102 = 4.9% [Wilson 95%: 2.1%, 11.0%]
    zh: other failures 17/102 = 16.7% [Wilson 95%: 10.7%, 25.1%]; the item claim 37/102 = 36.3% [Wilson 95%: 27.6%, 45.9%]
  arm B, a failure other than claiming to have seen the item: 0/204 = 0.0% [Wilson 95%: 0.0%, 1.8%]
    en: other failures 0/102 = 0.0% [Wilson 95%: 0.0%, 3.6%]; the item claim 0/102 = 0.0% [Wilson 95%: 0.0%, 3.6%]
    zh: other failures 0/102 = 0.0% [Wilson 95%: 0.0%, 3.6%]; the item claim 0/102 = 0.0% [Wilson 95%: 0.0%, 3.6%]
  arm C, a failure other than claiming to have seen the item: 24/204 = 11.8% [Wilson 95%: 8.0%, 16.9%]
    en: other failures 10/102 = 9.8% [Wilson 95%: 5.4%, 17.1%]; the item claim 6/102 = 5.9% [Wilson 95%: 2.7%, 12.2%]
    zh: other failures 14/102 = 13.7% [Wilson 95%: 8.4%, 21.7%]; the item claim 58/102 = 56.9% [Wilson 95%: 47.2%, 66.1%]
  arm A, item claims by someone whose public motive ties them to the item: 15/42 = 35.7% [Wilson 95%: 23.0%, 50.8%]
  arm C, item claims by someone whose public motive ties them to the item: 14/64 = 21.9% [Wilson 95%: 13.5%, 33.4%]
  sessions with another failure, B vs A: only B 0, only A 26 of 204 pairs; exact McNemar p = 2.98e-08
  sessions with another failure, C vs A: only C 16, only A 18 of 204 pairs; exact McNemar p = 0.864
  sessions with another failure, B vs C: only B 0, only C 24 of 204 pairs; exact McNemar p = 1.19e-07
```
