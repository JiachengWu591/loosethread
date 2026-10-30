# Change proposals

Strategic changes need owner approval before they take effect (see `CLAUDE.md`). Each proposal
keeps its data so the decision can be revisited. Status: `open` / `approved` / `rejected`.

Batch data below: `python -m loosethread.case --batch 1000 --metrics --rule {naive,trusting}`,
seeds 0–999, default parameters (5 suspects, 8 slots, window 3, 6 evidence items, occupied-room
alibi style). Full outputs: `docs/review/p1/batch-naive.txt`, `docs/review/p1/batch-trusting.txt`.

---

## CP-1 — `min_questions` is exact only up to 2; above that it is an upper bound · `approved`

- **Decision** (owner, 2026-10-30, "全部按建议"): option A; C to be evaluated in P2. See D-015.

- **Trigger**: an exact minimum is a set-cover search over ~150 distinct answers per case. Exact
  search at size 3 would need ~550k solver checks per case (minutes). Current implementation proves
  0, 1 and 2 exactly (all single answers, then both sides of every conflict) and otherwise reports a
  greedy-then-pruned upper bound. With the trusting rule, 211/1000 cases have an exact value (all of
  them 2); the other 789 have an upper bound in 3–10 and a proven lower bound of 2.
- **Impact**: P1 work item 5 (difficulty metrics) and any difficulty filter built on it (CP-3).
  No exit criterion depends on it.
- **Options**
  - A. Keep the current definition and always label values above 2 as "≤ n (upper bound)". Cost:
    filters on it are approximate.
  - B. Exact search with a time cap (seconds per case). Cost: too slow for generation-time filtering;
    usable only offline.
  - C. Add a second, behavioural metric in P2: questions needed by a simulated systematic player
    (e.g. asks each suspect about each window slot in random order), averaged over orders. Cost: a new
    metric to define and validate against the P2 playtest.
- **Recommendation**: A now; evaluate C during P2 with playtest data, since the oracle minimum
  assumes the player already knows whom to ask about which slot.

## CP-2 — Make "needs a contradiction" stricter (naive → trusting) · `approved`

- **Decision** (owner, 2026-10-30): option B; trusting is the default. See D-015.

- **Trigger**: DESIGN §10's naive criterion ("believing every statement evidence does not refute
  leaves no suspect") accepts cases that never require resolving a contradiction. In the naive batch,
  715/1000 = 71.5% [Wilson 95%: 68.6%, 74.2%] accepted cases are solved uniquely by the uncontested
  statements alone (`contradictions_required = 0`): the culprit is simply the only suspect without a
  corroborated alibi, and the alibi lie is irrelevant.
- **Impact**: the P1 acceptance rule (DESIGN §10), rejection rate and generation time. Exit criteria
  are met under both rules.
- **Data**

  | | naive (current) | trusting (proposed) |
  |---|---|---|
  | audited unique + all guarantees | 1000/1000 [99.6%, 100%] | 1000/1000 [99.6%, 100%] |
  | attempts rejected | 35.5% [33.2%, 37.9%] | 81.5% [80.5%, 82.5%] |
  | generation time mean / p95 / max | 0.007 / 0.012 / 0.033 s | 0.028 / 0.075 / 0.220 s |
  | `contradictions_required` = 0 | 715 | 0 |
  | `min_questions` = 1 or 2 | 278 | 211 |

- **Options**
  - A. Keep naive. Cost: about 7 in 10 cases do not need contradiction reasoning, against the brief.
  - B. Trusting: the uncontested statements alone must leave at least two suspects. Cost: more
    rejected attempts; still far under 1 s per case.
  - C. Use naive for an easy mode and trusting for normal/daily.
- **Recommendation**: B as the default (C can be added later as a difficulty option).

## CP-3 — Revisit the daily-case difficulty target (min questions 6–10) · `approved`

- **Decision** (owner, 2026-10-30): option B; provisional target 3–6, budget 20, revisit after the
  P2 playtest (option C only if cases prove too easy). See D-015.

- **Trigger**: under T2 one conflict between the culprit and a witness narrows the culprit to two
  people, so an oracle needs few questions. Trusting-rule distribution of `min_questions`
  (2 exact, others upper bounds): 2: 211, 3: 477, 4: 177, 5: 79, 6: 43, 7: 11, 9: 1, 10: 1. Only
  56/1000 = 5.6% [4.3%, 7.2%] fall in 6–10.
- **Impact**: DESIGN §10 daily target and question budget; P4 daily case. Filtering to 6–10 would
  multiply attempts by ~18 and risks the < 1 s generation criterion; it would also filter on an upper
  bound (CP-1).
- **Options**
  - A. Keep 6–10. Cost: slow generation, and the filter is approximate.
  - B. Provisional daily target `min_questions` 3–6 (776/1000 trusting cases; excludes the
    two-question cases), keep the budget at 20, and set both after the P2 playtest.
  - C. Make cases structurally harder (window of 4, 6 suspects, culprit lying about two slots) and
    re-measure. Cost: changes DESIGN scale defaults; more generator work.
- **Recommendation**: B now; try C in P2 only if the playtest says cases are too easy. The oracle
  number understates human effort because players do not know whom to ask about which slot.

## CP-4 — Sub-agent instead of the owner for review cases 214 and 222 · `approved`

- **Decision** (owner, 2026-10-30, "批准 B"): option B, including the P2 playability-gate question.
  See D-017.

- **Trigger**: the owner solved case 213 by hand and found no problem. Their view: anyone patient
  enough to tabulate the testimony and look for the contradiction reaches the answer, so the other
  two manual reviews add little; they propose that a sub-agent solves 214 and 222. Supporting data:
  the independent solver proves a unique solution for 1000/1000 seeds, and in the trusting batch
  `contradictions_required` is 1 for 992/1000 cases (2 for 8), so most cases share 213's shape.
- **Impact**: lowers the P1 exit criterion "the owner reviews 3 cases by hand and can deduce the
  culprit" to one case by hand plus two by sub-agent. Lost: human evidence on the hardest case (222,
  where an innocent's exposed lie is a red herring). A sub-agent success shows that the sheet is
  self-contained for a careful reader, not that a person finds it readable or fun; those questions
  move to the P2 playability gate. No schedule impact; saves the owner about 20–40 minutes.
- **Options**
  - A. Keep the criterion: the owner solves 214 and 222. Cost: owner time.
  - B. One sub-agent per case, fresh context, given only the `-player.txt` (which includes the
    rules). It must name the culprit and one pair of items that cannot both be true, one of them a
    statement by the culprit (the DESIGN §9 accusation). Pass = right culprit and the pair exposes
    one of the culprit's lies, checked against `-full.txt`. Anything else, including no parseable
    answer, is a fail, and the owner then solves that case by hand. Cost: as under Impact.
- **Recommendation**: B. With an exact solver behind every case and 213 showing the sheet is fair
  to a person, two more manual reviews add little. Also add to the P2 playability gate the question
  "do cases feel formulaic?", since 99.2% of cases need exactly one contradiction.
