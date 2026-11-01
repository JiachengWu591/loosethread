# Parser question set

`questions.jsonl`: 199 player questions (119 zh, 80 en) with the query each one should become.
Used to measure parser accuracy (ROADMAP P2 work item 9; plan in D-018).

**Status: frozen 2026-10-31** (D-022). SHA-256 of `questions.jsonl`:
`13e22acc0eaf413cfede733e6138169ccdb9e668fada5db0c14060b0ba57d60d`, also in
`loosethread.parser_eval.FROZEN_SHA256`; the evaluation refuses any other version. The owner
spot-checked 30 random items (`docs/review/p2/parser-spotcheck.md`) and found no wrong label:
30/30, so the label error rate is below 11.4% (Wilson 95% upper bound); the check cannot rule out
a few wrong labels among the other 169 items.

## The settings check (not part of the frozen set)

`settings-check.jsonl`: 36 plain questions (20 zh, 16 en) with the names of the two newer settings
(D-031), each read once by each backend. Its only job is to show that a parser takes the new names;
it is plain on purpose, has no spoken forms, ranges or injections, and its score says nothing about
the frozen set's measure. Its SHA-256 is `loosethread.parser_eval.SETTINGS_SHA256`.

## Provenance and limits

- Drafted and labelled by an LLM (Claude), as approved in D-018; the owner spot-checks 30 items.
  Questions written by the same kind of system that is being evaluated may be easier or more
  uniform than real players' questions; the owner's playtest log (`docs/review/p2/`) is the only
  real-player sample so far.
- Three daily cases with different casts: seeds 213, 7 and 42 (all nine characters, all three
  stolen items, all seven rooms). Labels use public names only; no truth is involved.
- Deliberately included: colloquial and spoken Chinese times (差一刻九点, 九点过一刻), English
  clock words ("twenty to ten", "2045"), roles and paraphrased roles ("the owner", 修车的), a person
  named next to the item ("Mr Shen's seal"), injections and who-did-it questions, ranges, relative
  times, times outside the evening, two people in one question.

## Format

One JSON object per line:

| field | meaning |
|---|---|
| `id` | `zh001`...; stable |
| `split` | `dev` (51, for tuning prompts) or `test` (148, measured once per backend) |
| `lang`, `seed`, `addressee` | the case and the person asked |
| `question` | the raw text, as a player would type it |
| `expect` | `{"kind": ..., "slot"/"person"/"location"/"item": ...}` or `{"clarify": reason}` |
| `also` | other labels that are equally right (rare; listed in the spot-check) |
| `tag` | what the item exercises (`zh_time_hard`, `role`, `injection`, ...) |

Labelling rules: "you" is the addressee; a time inside a slot means that slot and a range that is
exactly one slot means that slot; a question naming one place and one time is `where`; a question
about another person and a time is `saw_person` with that slot; anything that should make the
player rephrase is a `clarify` with the reason the game would give.

## Scoring (fixed before the first measurement)

- **Accuracy** (the P2 exit criterion, >= 85% on DeepSeek, test split): the parse equals `expect`
  or an `also` label. All clarify reasons count as one outcome (any "please rephrase" is right
  when a rephrase is expected), because the reason only changes the hint text.
- **Strict accuracy**: clarify reasons must match too.
- Errors are split by what they cost the player:
  - *charged wrong*: a query other than the expected one, or a query where a rephrase was
    expected; the player pays a question for an answer to something they did not ask;
  - *needless rephrase*: a rephrase where a query was expected; free, but annoying;
  - *invalid*: the backend replied with something unusable; counted separately, never as
    correct. In the game it becomes a free rephrase.
- The model parser is reported with and without the time guard (one model call per item;
  the guard is deterministic). Every rate gets a Wilson 95% interval; backends are compared on
  the same items with an exact McNemar test.
- The P2 criterion is judged on the guarded variant, the parser as the game runs it (stated
  before the DeepSeek test, D-024).
