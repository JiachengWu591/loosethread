# Loose Thread: evaluation report (P3)

**Status: complete, signed off by the owner on 2026-11-03.** Every number here is recomputed from the raw rows by
`python -m loosethread.verify` and appears in `results/*.md`. Plan: `docs/STUDY_PLAN.md`. Changes to it: §15 there, and
`docs/DECISIONS.md` D-035 to D-042.

## 1. What the results say

The project's thesis (`docs/BRIEF.md` §2) was that *structural isolation, not prompt instructions, keeps LLM NPCs
from both making things up and being talked into leaking.* The results support part of that and go against part.

- **Making things up: the layered pipeline did better, by less than the headline suggests.** B had no flagged
  failure in 204 interrogations, against 60 in the prompt-only arm. Most of A's failures are one claim on one question,
  and about half of the others are scoring errors. The direction survives both corrections. Withholding the truth
  alone did not help: arm C failed at least as often as A. What helped was the pipeline, not the missing truth.
- **Being talked into leaking: the thesis is not supported.** No arm leaked in 200 static attacks. An unhardened
  prompt under the same attacks did, 19 times. So these attacks can cause leaks, and with this model a hardened
  prompt was enough to stop them. No confirmed leak came from about 2,000 adaptive attacks either.
- **An LLM can write a solvable case in one shot, if it may think.** H1 predicted that fewer than half would pass;
  83.3% did. With thinking off, none did.
- **The pipeline's costs are real, but its valid-answer rate is not one of them.** That rate was not lower. It takes
  about twice as long and repeats itself far more. In one person's blind rating, its lines sounded less like a person in
  20 of 30 pairs, which leans the way H5 predicted without clearing chance (p = 0.099).

No person checked the labels, flags or leak decisions behind these numbers: two runs of one LLM did, at the
owner's request (§6). The one measure a person made is the rating of lines.

![Failure and leak rates per arm, with 95% Wilson intervals](../results/figure.svg)

## 2. Setup

- **System**: the shipped game at a recorded commit. **Model**: `deepseek-flash` (served by DeepSeek-V4.1-Flash-1017),
  temperature 0. **Cases**: 204 held-out generated cases, 102 zh and 102 en, across 3 settings and 4 lie shapes.
- **Arms**: **A** prompt-only, with the whole case including the truth, under hardened instructions. **B** layered:
  parser, answer table, writer and post-check, where the writer sees neither the truth nor the raw question. **C**
  claims-only: A's prompt without the truth. **U** (added after the results, in no hypothesis): the truth under one
  plain sentence, with no hardening.
- **Statistics**: Wilson 95% intervals on rates, exact McNemar on pairs, Holm across the two primary tests. A failed
  call is its own category, never a pass.

## 3. Results

### H1 to H5

| Hypothesis | Result | Verdict |
|---|---|---|
| H1: fewer than half of one-shot cases pass | thinking on, 50/60 = 83.3% [72.0%, 90.7%] | **Fails** |
| H2 (primary): fewer B than A sessions with a failure | B 0/204, A 60/204; exact p = 1.7e-18, Holm 3.5e-18 | Holds, with §3.2's caveats |
| H3 (primary): fewer attacks leak in B than in A | B 0/200, A 0/200; no discordant pair; p = 1 | **Fails** |
| H4: A leaks more than C | A 0/200, C 0/200 | **Fails** |
| H4: C fails more than B | C 76/204, B 0/204; exact p = 2.7e-23 | Holds, with §3.2's caveats |
| H5: B less valid than A | B 100.0% [99.7%, 100%], A 96.2% [95.0%, 97.2%] | **Fails**, in B's favour |
| H5: B rated less natural | A preferred in 20 of 30 pairs, B in 10; exact sign test p = 0.099; one rater, descriptive | Leans as predicted, not shown |

### 3.1 RQ1: can an LLM write a case in one shot?

| Setting | Accepted | Other verdicts | Per case |
|---|---|---|---|
| Thinking on, 60 cases | 50 = 83.3% [72.0%, 90.7%] | too easy 7, multiple 1, invalid 2 (1 failed call, 1 cut off) | about CNY 0.22, median 156 s |
| Thinking off, 204 cases | 0 = 0.0% [0.0%, 1.8%] | self-contradictory 204 | about CNY 0.01, median 4 s |

The generator's 204 test cases all pass the same checker, by construction, which checks the checker and nothing
more. Its attempts pass 300/2304 = 13.0% [11.7%, 14.5%]. That compares one-shot writing with generate-and-check, and
is not a contest. The generator costs nothing per case, is deterministic, and never ships a case that fails. The
LLM's cases passed the logic checks only: the generator's difficulty filter and its evidence check were not applied,
and nobody has played them.

### 3.2 RQ2: does the NPC say what it may not?

| Arm | Sessions with a failure, as registered | Without the item claim (post hoc) | Valid answers, turns 1 to 6 |
|---|---|---|---|
| A | 60/204 = 29.4% [23.6%, 36.0%] | 26/204 = 12.7% [8.8%, 18.0%] | 96.2% [95.0%, 97.2%] |
| B | 0/204 = 0.0% [0.0%, 1.8%] | 0/204 = 0.0% [0.0%, 1.8%] | 100.0% [99.7%, 100%] |
| C | 76/204 = 37.3% [30.9%, 44.1%] | 24/204 = 11.8% [8.0%, 16.9%] | 94.6% [93.2%, 95.7%] |

Pairs: only A 60, only B 0 (p = 1.7e-18); only C 76, only B 0 (p = 2.7e-23); only C 29, only A 13 (p = 0.020). Without
the item claim: B against A p = 3.0e-8; C against A only C 16, only A 18 (p = 0.86).

**Three things limit this result.** The first two were found by reading the failures, after the fact.

1. **One question carries most of it.** Sessions in which A claims to have seen the item: zh 37/102, en 5/102. "你见过X吗"
   also means "have you ever seen X", and 15 of A's 42 such lines (35.7%) come from a character whose public motive
   ties them to the item, such as once bidding for it. The answer table knows none of this. The flag is correct by
   the plan's rule, and the rule is the system's own, so the question favours B.
2. **Many other flags are scoring errors.** In a review of flagged lines (§6), the item claim stood 6/6 [61.0%, 100%],
   and other failures stood only 11/24, 45.8% [27.9%, 64.9%]. Most errors read a loose span as a fixed slot, or give
   a statement the question's time. These errors fall on the longer lines of A and C. If that share held, about 12 of
   A's 26 would be real. That is a rough figure, as the sample was drawn by line, not session.
3. **The extractor missed its target.** 26/30 lines read right, 86.7% [70.3%, 94.7%], below the plan's 27. As the plan
   requires, it was not retuned, and this caveat stands. All 4 misses are in A or C, and all lose a span or a wider denial,
   so they can hide failures as well as create them.

B's 100% comes from well-formed scripted questions. On natural phrasing the parser scored 93.2% [88.0%, 96.3%] (P2).

### 3.3 RQ3: can the NPC be talked into leaking?

| Arm | Static attacks that leak, after review | Before review |
|---|---|---|
| A, hardened prompt | 0/200 = 0.0% [0.0%, 1.9%] | 3 |
| B, layered | 0/200 = 0.0% [0.0%, 1.9%] | 1 |
| C, claims only | 0/200 = 0.0% [0.0%, 1.9%] | 2 |
| U, no hardening (post hoc) | 19/200 = 9.5% [6.2%, 14.4%] | 20 |

U against A: only U 19, only A 0, exact p = 3.8e-6. U accused someone 10 times, each time the real culprit, so these
are not lucky guesses. Two of U's 19 say nothing true about where anyone was, and single out the culprit's story;
on the plan's strict wording U would be 17/200. Leaving out 22 attacks whose stated goal cannot be met changes
nothing: A, B and C stay at 0/178, and U is 18/178.

Before review, the six flags in A, B and C were five exact-match false alarms on a repeated account or a rejected
claim, and one failed judge call that counts as a leak by rule. Exact matching and the judge are both rough; §6 shows
what each can see.

**Adaptive campaigns**: an attacker LLM with the score of its past attempts, 5 attacks a round for 100 rounds, on the
culprit of one case per language. No confirmed leak in 500 (A, zh), 502 (A, en), 500 (B, zh) or 500 (B, en) attacks.
"None found in this many" is the strongest claim this allows. These attacks depend on one another, and other work saw
prompt defences hold for tens to hundreds of rounds and then fall (Deep et al. 2026), so longer campaigns could
end differently. U had no adaptive campaign.

**How to read this**: B cannot state the truth because its writer never receives it, so its zero is close to
guaranteed and is weak evidence alone. A's zero rests on the model obeying its prompt. This study shows that A held, on
this model, for single turns and 100 rounds. It cannot put a number on what B's guarantee is worth, because A
did not fail here.

### 3.4 What the pipeline costs

| Per session, RQ2 | A | B | C |
|---|---|---|---|
| Seconds, median (p95) | 9.1 (10.3) | 17.1 (18.7) | 9.0 (10.1) |
| Tokens, median (p95) | 18,966 (19,804) | 21,272 (21,544) | 11,202 (11,517) |
| CNY, upper bound, median | 0.059 | 0.063 | 0.043 |
| Sentences repeating one in the session | 1.1% [0.8%, 1.6%] | 17.7% [16.2%, 19.4%] | 1.4% [1.0%, 2.0%] |
| Median line length, zh characters / en words | 25 / 18 | 29 / 13 | 24 / 18 |

No B line was replaced by the template (0/1632). 23 of 200 attacks, 11.5% [7.8%, 16.7%], cost a player a charged
question in B.

**Natural-sounding lines.** The owner rated 30 pairs of A and B lines to the same question, with sides shuffled and
arms hidden. B sounded more like a person in 10/30, 33.3% [19.2%, 51.2%]: A 20, B 10, no ties, exact sign test
p = 0.099. Each language split the same way, A 10 to B 5. This leans the way H5 predicted, and the interval still
includes an even split. Only 1 of the 20 A lines that won carries a failure flag (post hoc), so the preference is not
mostly for lines that say what they may not, though flags have the errors §3.2 describes.

There is one rater, who commissioned the system and has played B's lines. Those lines also have a recognisable form
("Between 20:30 and 20:45 ..."), so hiding the arm may not have hidden it. This says nothing about whether players
mind. Related work also found stiffness as a cost (Figueiredo & Elumeze 2025; Rahmati & Zhao 2026).

### 3.5 Stability

20 turns per arm asked again, each the speaker's first. A turn with no usable reading does not agree.

| Same in both runs | A | B | C |
|---|---|---|---|
| Line, word for word | 11/20 | 18/20 | 12/20 |
| Extracted claims | 18/20 | 19/20 | 16/20 |
| Failures | 20/20 | 19/20 | 18/20 |

B's and C's misses on the last two rows include one connection failure each. With n = 20 these are descriptive, and
each interval is wide (`results/repeat.md`).

## 4. What this does not show

- Whether the game is fun, or how real players behave. Questions were scripted or written by an LLM.
- Anything beyond one model family at one time. Another model might leak under arm A, or write no valid case.
- Security against attackers not modelled here. Static attacks are single-turn, and adaptive campaigns cover one case
  per language and only the culprit.
- That B is safe in general. Its parser, answer table and post-check were tested here on these inputs only.
- Anything about other games. The cases are ours, and the answer table that defines "may say" is the system's own design,
  so B is judged by its own rules.

## 5. Changes from the plan

All are recorded in `docs/DECISIONS.md` and `docs/STUDY_PLAN.md` §15.

- **Added after reading results, in no hypothesis**: arm U; RQ2 without the item claim; a review of flagged lines; a
  control of the judge on written replies.
- **The owner's checks were delegated.** The attack sample and four of five sheets were read by Claude subagents, not by
  the owner. The owner made this decision, and it is the study's largest departure from its plan. The owner did the
  fifth, the blind rating of lines, as planned.
- **The attacker's output limit rose from 600 to 1200 tokens during the test run**, because it cut off the A/en campaign's
  JSON. That campaign's round numbers run to 107 so that it also got about 500 attacks. Connection failures stopped it
  twice. The other three campaigns were never cut off and finished at 600.
- **A failed call**: in RQ3 it was retried once on resuming, with both attempts kept. A failed judge call was reviewed like
  a disagreement. The outage guard counts only the calls of the current run.
- **RQ1** runs in two settings, and `deepseek-pro` was dropped (CP-9).
- **Costs** are upper bounds at prices from 2026-10-31, which could not be re-read before the pilot. The study came to
  CNY 78.32 of the CNY 80 cap.

## 6. How far the measurements can be trusted

| Check | Result | What it cannot detect |
|---|---|---|
| Judge on written replies with known answers | flags 38/40 that leak, 0/24 that do not | Subtle leaks: these replies are plain |
| Exact matching on the same replies | flags 16/40, 0/24; any negation in a line turns it off | Most paraphrase |
| Extractor, 30 lines read | 26/30 = 86.7% [70.3%, 94.7%], below the plan's 27 | A sample of 30 cannot say which errors are rare |
| Flagged lines, 30 read | item claim 6/6; other failures 11/24 | Failures nobody flagged |
| Attack labels, 30 read | 2 wrong, 11 borderline, none past the content limits | The 170 unsampled attacks; attack strength |
| Line pairs, 30 rated by the owner | A 20, B 10, no ties; p = 0.099 | Any other rater's taste; whether players mind |
| Run-to-run repeat | §3.5 | Drift between days or model versions |

The two reviewers of the four sheets agreed on 85/85 items. They are one model run twice, so this does not show that
independent judges would agree. The attacks were written by an LLM and their sample reviewed by an LLM. Labels on the
attacks are often arguable, so results by goal are not reported, and results by category are descriptive.

Scoring favours B in one more way. B writes short, regular lines, which give the extractor less to misread, and judges
of this kind are known to favour regularity (Figueiredo & Elumeze 2025).

## 7. Related work

Rahmati & Zhao (2026, arXiv 2609.23043) tested a pipeline in an LLM detective game with 33 participants, and report
critical hallucinations of 17.80% against 6.27% of responses, with usability costs. It has a human study, which this
project lacks. It has no systematic attack test, a limit this project addresses in part. Deep et al. (2026, arXiv
2604.23887) and Ma et al. (2026, arXiv 2606.15057) show that static sets and short runs overstate defences, which is why
the adaptive arm exists and why its result must be read with care. Full list: `docs/RELATED_WORK.md`.

## 8. Reproducing this

```bash
uv run python -m loosethread.verify
```

It needs no key and makes no model call. It recomputes every table and the figure from `results/rows/` and exits 1 on
any difference. It repeats every scoring decision from the raw rows. It cannot show that the rows came from the calls
they describe, or that a model would answer the same way again.
