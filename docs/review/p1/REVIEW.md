# P1 review of cases 213, 214 and 222

The P1 exit criterion "the owner reviews 3 cases by hand and can deduce the culprit" was changed
by CP-4 (D-017). Under the changed criterion, the owner solves one case by hand. For each of the
other two, a fresh sub-agent sees only the player sheet and must give the culprit plus a pair of
items that cannot both be true, one of them a statement by the culprit. A case passes when the
culprit is right and the pair exposes one of the culprit's lies (checked against `-full.txt`).

## Results (2026-10-30)

| Case | Solved by | Culprit given | Pair given | Answer key | Result |
|---|---|---|---|---|---|
| 213 | owner, by hand | owner reports solved | — | 何秀兰 | pass; no problems found |
| 214 | sub-agent | 陈墨 | 陈墨 says 21:15 alone in 大堂 ↔ 林小雨 says 21:15 alone in 大堂 | 陈墨; alibi lie exposed by 林小雨 | pass |
| 222 | sub-agent | 陈墨 | 陈墨 says 21:15 alone in 大堂 ↔ 赵一帆 says 21:15 alone in 大堂 | 陈墨; alibi lie exposed by 赵一帆 | pass |

- **Owner feedback (213)**: the logic was fine, but the sheet was "too rigid" to read. This led
  to the case-sheet layout in D-016, and all three sheets were regenerated before the
  sub-agent runs. The case data did not change.
- **Sub-agent setup**: each run started with a fresh context (not a fork of the authoring
  session). The prompt held only the task, the required answer format, and the full
  `-player.txt` text. It also told the sub-agent to use no tools. The recorded tool-use count was
  0 for both runs. The runs took about 56k and 58k tokens, and 48 s and 58 s.
- **Sub-agent reasoning**: both runs reached the answer the same way:
  1. Use the owner's in-window testimony as fixed facts.
  2. Find the "two people alone in one room" conflict.
  3. Rule out the other party in the conflict with a reachability argument to the study.
  4. Check that the culprit could have been alone in the study at 21:15.

  The 222 run also correctly dismissed both innocent privacy lies as red herrings: 赵一帆 at
  20:00 (exposed by E2) and 周大川 at 20:15 (exposed by E3). We checked each step against the
  sheet and found no errors.

## What this does and does not show

- **What the sub-agent passes show**: the sheet is self-contained. A careful reader with only the
  printed rules can find the contradiction and close the case. They do not show that a person
  finds it readable or fun. The human evidence comes from one case, 213.
- **Model bias**: the sub-agents are the same model family as the sheet's author, so they may
  share its reading habits.
- **The "no tools" rule**: it was an instruction, not a sandbox. The tool-use count of 0 is
  evidence that it was followed.
- **Sample size**: n = 2. This is a review check, not a measurement.

## Variety of generated cases

The three review cases all put the theft in the 21:15 slot. In two of them, the culprit claims to
have been in the lobby. To see whether this is a pattern, we ran
`uv run python docs/review/p1/variety.py` over seeds 0–999 with default parameters. All
intervals are Wilson 95%.

- **Theft slot position in the 3-slot window**:
  - 1st: 27.7% [25.0%, 30.6%]
  - 2nd: 42.3% [39.3%, 45.4%]
  - 3rd: 30.0% [27.2%, 32.9%]

  By clock time, 21:15–21:30 is 19.3% [17.0%, 21.9%]. All three cases landing there is chance.
- **Culprit**: all 8 roster members appear, each 11.6%–14.2%.
- **Room the culprit claims in the alibi lie**:
  - lobby: 42.2% [39.2%, 45.3%]
  - kitchen: 27.9%
  - guest wing: 18.8%
  - corridor: 11.1%
  - tea room, dining room: never
- **Number of items that expose the alibi lie**:
  - 1: 48.3%. A single witness says they were alone.
  - 2: 51.7%. Two witnesses name each other and leave the culprit out.
- **Innocent privacy lies per case**: 0 in 29.7%, 1 in 33.9%, 2 in 36.4%.

**Reading**: the surface details vary, but the shape of the deduction does not. Every case uses
the occupied-room alibi, and 99.2% need exactly one contradiction. CP-4 therefore added the
question "do cases feel formulaic?" to the P2 playability gate.
