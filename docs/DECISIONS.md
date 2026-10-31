# Decisions

Numbered decision records. Each: context, options, decision, consequences, date.
Strategic decisions reference the owner's approval (or change proposal); tactical ones are logged here
directly.

---

## D-001 — Project name: 破绽 / Loose Thread, package `loosethread`

- **Date**: 2026-10-30 · **Type**: strategic · **Approved by owner** (chat, 2026-10-30)
- **Context**: working name 「不在场证明」/ Alibi, package `alibi`. Name check (2026-10-30, PyPI /
  Steam / itch.io / GitHub):
  - PyPI `alibi` is taken (Seldon's ML explainability library); the import name would clash too.
  - Steam: Alibi, No Alibi, Devil's Alibi, Alibi for love, and others.
  - itch.io: about ten games titled Alibi, including two daily deduction puzzles (see RELATED_WORK).
- **Options**
  - 破绽 / Loose Thread (`loosethread`): free on PyPI and Steam; ~21 tiny GitHub repos; several itch.io
    items titled "Loose Thread(s)" (mostly tabletop/art packs).
  - Fibline (`fibline`): free everywhere checked; invented word, meaning unclear to players.
  - Liar's Ledger / 谎言账本 (`liarsledger`): free everywhere checked; long.
- **Decision**: 破绽 / Loose Thread. Package, import and distribution name `loosethread`.
  「不在场证明」 may be used as a subtitle.
- **Consequences**: all commands use `loosethread` (e.g. `python -m loosethread.verify`). The check did
  not cover trademark databases, app stores or domains; re-check before release (P5).

## D-002 — Local folder stays `E:\alibi`

- **Date**: 2026-10-30 · **Type**: tactical (owner agreed)
- **Context**: folder was created under the working name. The folder name does not affect the repo or
  package name.
- **Decision**: keep `E:\alibi`.
- **Consequences**: none for users; the GitHub repo can be named independently.

## D-003 — Licenses: MIT for code, CC BY 4.0 for content and data

- **Date**: 2026-10-30 · **Type**: strategic · **Approved by owner**
- **Options**: code MIT vs Apache-2.0 (explicit patent grant); content CC BY 4.0 vs CC BY-SA 4.0
  (share-alike).
- **Decision**: code MIT (`LICENSE`); content packs, experiment data/reports and media CC BY 4.0
  (`LICENSE-CONTENT.md`).
- **Consequences**: maximum reuse. `LICENSE-CONTENT.md` currently links to the license; the full legal
  code is vendored from creativecommons.org before v0.1.0 (ROADMAP P5) rather than typed from memory.

## D-004 — Case theme: theft in a closed setting; "culprit", not "murderer"

- **Date**: 2026-10-30 · **Type**: strategic · **Approved by owner**
- **Context**: content-safety rule prefers theft, sabotage or disappearance over violence. Items whose
  location changes over time make natural evidence.
- **Options**: theft at a closed location (recommended); sabotage before a school drama performance;
  museum/expo theft after closing.
- **Decision**: first content pack is a theft at a fictional mountain guesthouse on a rainy night
  (closed setting: the road is cut off), modern day, fictional place names. Sabotage and disappearance
  are later content packs.
- **Consequences**: all copy says 犯人 / 窃贼 / culprit, never 凶手 / murderer. Details in `DESIGN.md`.

## D-005 — Git bootstrap: first commits on `p0-skeleton`, `main` created at its tip

- **Date**: 2026-10-30 · **Type**: tactical
- **Context**: the rules forbid committing directly on `main`, but a new repository has no commit on
  `main` to branch from.
- **Decision**: `git init -b main`, then switch to `p0-skeleton` before the first commit. On approval,
  `main` is created at the tip of `p0-skeleton` (`git branch main p0-skeleton`), which is equivalent to
  a fast-forward. Later phases use the normal `merge --ff-only` flow.
- **Consequences**: `main` never receives a direct commit.

## D-006 — Tooling: uv + hatchling, uv-managed Python 3.12, `dev` as an extra

- **Date**: 2026-10-30 · **Type**: tactical
- **Context**: the machine's PATH Python is Anaconda 3.12.7; uv 0.7.11 is installed and has managed
  CPython 3.12.11.
- **Decision**
  - Build backend `hatchling` (mature, PEP 639 license metadata; avoids depending on the newer
    `uv_build` with an older local uv).
  - `.python-version` = 3.12, so uv picks its managed interpreter, not Anaconda.
  - Dev tools are the `dev` extra (as the brief specifies), not a PEP 735 dependency group:
    `uv sync --extra dev`.
  - `uv.lock` is committed; CI uses `uv sync --locked`.
  - Ruff rule set E, W, F, I, UP, B, SIM, RUF, PL, PT; RUF001–003 are ignored because Chinese text and
    full-width punctuation are intentional.
  - CI matrix: ubuntu-latest and windows-latest (catches encoding and path issues on the owner's OS).
  - `.gitattributes` forces LF so result rows are byte-identical across OSes.
- **Consequences**: contributors need uv. A stdlib-only guard test (`tests/test_package.py`) fails if
  a core module imports a third-party package; `loosethread.llm` and `loosethread.web` are exempt.

## D-007 — Data contract shape (first draft)

- **Date**: 2026-10-30 · **Type**: tactical
- **Context**: the brief lists Person, Location, TimeSlot, Item, Event, Fact, Statement, Evidence, Case,
  Query, AllowedFacts. The solver must not read truth, and the line LLM must only see `AllowedFacts`.
- **Decision**
  - All contracts live in `loosethread.model` as `@dataclass(frozen=True)`; collections are `tuple`
    or `frozenset`, so values are immutable and hashable. IDs are `NewType`s over `str`/`int`.
  - `Fact` is a PEP 695 union of small fact classes (`PersonAt`, `Occupants`, `ItemAt`) instead of one
    class with optional fields, so mypy and `match` see exact shapes.
  - `Case` is split into `PlayerView` (public; the solver's only input) and `Truth` (culprit, timeline,
    `Event`s, `Knowledge`, `Lie`s). Added types beyond the brief: `LocalizedText`, `World`, `Motive`,
    `CrimeReport`, `PlayerView`, `Truth`, `Knowledge`, `Lie`, and enums `Basis`, `Stance`, `Tone`.
  - `Statement` has no "is lie" field; lies are recorded only in `Truth.lies`.
  - Validation runs in `__post_init__` and raises `ValueError` (fail closed): e.g. a `Query` with
    missing or extra fields for its kind cannot be constructed.
  - Isolation is tested structurally: `tests/test_model.py` walks type annotations from `PlayerView`
    and `AllowedFacts` and asserts no truth type is reachable; a companion test checks that the walker
    does find truth types from `Case`.
- **Consequences**: the walker checks *types*, not values. It cannot catch truth leaking through a
  `str` field (e.g. a persona text that mentions the theft) or through code that reads `Truth` and
  copies facts into `AllowedFacts` incorrectly. Those need the P1 lie-policy tests and the P2
  prompt-interception tests.

## D-008 — Positioning: daily / solvable / share card are not differentiators

- **Date**: 2026-10-30 · **Type**: tactical (wording only; scope unchanged)
- **Context**: the name check surfaced non-LLM daily deduction puzzles (Alibi Grid, Alibi — Spot the
  Lie) that already offer a daily case, logic-solvable cases and an emoji share grid.
- **Decision**: keep these features (they serve players) but never present them as distinguishing.
  Positioning rests on natural-language interrogation over a solver-verified world model, structural
  isolation, and measured leakage and cost.
- **Consequences**: BRIEF §4 and RELATED_WORK updated. No change proposal needed because scope, phases
  and exit criteria are unchanged.

## D-009 — Game design review: all DESIGN §11 proposals accepted

- **Date**: 2026-10-30 · **Type**: strategic · **Approved by owner** (chat: "1–8 按建议")
- **Context**: DESIGN.md first draft listed eight open questions with a proposal for each.
- **Decision**
  1. Truthfulness contract T1–T5: innocents never lie inside the theft window; every innocent lie
     outside it is exposed by evidence; the culprit may lie freely, with at least one exposable lie.
  2. The full evidence file is given at the start.
  3. Every parsed question costs 1, including opinion and small talk; parse failures and exact repeats
     are free.
  4. Contradiction hints are on by default and off in hard mode.
  5. A valid accusation proof exposes any lie of the culprit.
  6. One accusation per case.
  7. 8 slots × 15 minutes, 20:00–22:00.
  8. Setting: Mistpine Lodge with the roster in DESIGN §1.
- **Consequences**: P1's solver implements the consistency rule in DESIGN §10 exactly, and the
  generator must guarantee T3 (each innocent lie has an evidence item that contradicts it). Deferred
  alternatives (innocent lies inside the window, searchable rooms, free small talk, two accusations,
  30-minute slots) can be revived after the P2 playtest by a new decision with owner approval.

## D-010 — Contract changes for P1: `Testimony`, `Stance.DENY`

- **Date**: 2026-10-30 · **Type**: tactical
- **Context**: difficulty metrics need to know which statements one question yields; some answers are
  denials ("I was never in the kitchen") with no structured claim.
- **Decision**: `PlayerView.testimony: tuple[Testimony, ...]` (query → claims) replaces the flat
  statement list; `PlayerView.statements` is now a derived, de-duplicated property. New
  `Stance.DENY`. Only answers with claims are recorded as testimony.
- **Consequences**: the solver ignores denials, which makes it slightly more conservative than a
  player (it may reject a case a player could solve, never the reverse).

## D-011 — Solver: exact per-person bitmask DP; conflicts include impossible moves

- **Date**: 2026-10-30 · **Type**: tactical
- **Decision**
  - All constraints are unary or within one person's consecutive slots, so for a fixed theft slot the
    persons are independent; each is a reachability check over location bitmasks.
  - "Direct conflict" covers the same slot (W1) and consecutive slots (W2); "contradicted by
    evidence" uses the same definition (DESIGN §10).
  - Inconsistent evidence fails closed (no hypothesis survives).
  - The solver imports nothing from the generator, lookup, audit or content modules and no truth
    types; `tests/test_isolation.py` checks this by AST.
- **Verification**: `tests/test_solver.py` compares the solver with brute-force enumeration of whole
  joint timelines (independent code) on 140 random small problems, in full, naive and partial-
  testimony modes. It found one real bug during development (a contradictory second evidence item
  was silently ignored), now fixed.
- **Limits**: brute force covers 2–3 people, 3 locations and 3–4 slots; larger cases rely on the
  decomposition argument plus the generator-level property tests.

## D-012 — Generator design choices

- **Date**: 2026-10-30 · **Type**: tactical
- **Decision**
  - Timelines: backward-feasibility DP + weighted random walk. Weights favour the character's haunts
    (new `haunts` field in the content pack), staying put and small groups; crowds of 3+ and the crime
    scene are rare. Innocents never enter the crime scene during the window (otherwise the case
    cannot be unique).
  - The client is a non-suspect who always tells the truth; the client's photo fixes *last seen*.
  - Culprit alibi lie: occupied-room style by default; the unreachable-room style is available but
    off (DESIGN §5). Measured on seeds 0–149 with the trusting rule: unreachable-only gave a
    two-question solution in 149/150 cases (self-contradicting story); occupied-only gave a median
    of 3 questions (range 2–7). Witnesses of the alibi lie are suspects, never the client.
  - Innocent privacy lies: 0–2, outside the window, each contradicted by an evidence item that
    places the liar truthfully.
  - Evidence guard: no evidence that alone breaks the culprit's alibi; specific templates preferred;
    at most two evidence items per person; evidence order shuffled so ids do not reveal which items
    expose lies.
  - Hearsay: 0–2 items, "B told A, at a later slot they shared, where B was".
  - Determinism: each attempt uses `random.Random(f"loosethread:{pack}:{seed}:{attempt}")`; no
    iteration over hash-ordered sets affects choices (tested across `PYTHONHASHSEED` values).
  - `audit.py` checks every guarantee against the ground truth independently of the solver's
    reasoning.

## D-013 — Difficulty metric definitions

- **Date**: 2026-10-30 · **Type**: tactical (first definitions; see CP-1 for the min-questions caveat)
- **Decision**
  - `contradictions_required`: fewest conflict groups (connected contested statements) that must be
    taken into account, on top of all uncontested statements, before the culprit is unique.
  - `min_questions`: greedy choice of answers (most suspects ruled out, then fewest feasible
    theft-slot pairs) followed by reverse pruning. Exact only when it is ≤ 1, or 2 after every single
    question was shown to be insufficient; otherwise an upper bound.
  - `inference_steps`: for each innocent suspect, the size of an irreducible (deletion-minimal)
    statement set that still rules them out, summed.

## D-014 — Lint and test configuration

- **Date**: 2026-10-30 · **Type**: tactical
- **Decision**: ignore ruff's size rules PLR0911/0912/0913/0915/0917 (they fight the generator's
  step-by-step orchestration and the audit checklist); set pytest `python_classes = []` so model
  classes such as `Testimony` are not collected as tests.

## D-015 — Change proposals CP-1, CP-2, CP-3 approved

- **Date**: 2026-10-30 · **Type**: strategic · **Approved by owner** (chat: "全部按建议")
- **Context**: `docs/CHANGE_PROPOSALS.md` (data from 1,000-seed batches under both rules).
- **Decision**
  - CP-1: `min_questions` stays exact up to 2 and an upper bound above; always labelled. A behavioural
    "simulated player" metric is to be evaluated in P2.
  - CP-2: the acceptance rule requires at least two suspects to remain consistent on uncontested
    statements alone (`ContradictionRule.TRUSTING`, now the default). Naive remains available.
  - CP-3: daily preset `generator.DAILY` = minimum questions 3–6; budget 20; both revisited after
    the P2 playtest.
- **Consequences**: default generation rejects ~81.5% of attempts (mean 0.028 s, max 0.22 s per
  case on seeds 0–999). Daily preset on seeds 0–299: mean 0.118 s, p95 0.334 s, max 0.63 s per case.
  DESIGN §10 updated.

## D-016 — Case sheet layout for the debug CLI

- **Date**: 2026-10-30 · **Type**: tactical
- **Context**: the owner solved review case 213 and found the sheet correct but "too rigid" to read
  (long `|`-separated lines, no rules, adjacency as a list).
- **Decision**: `python -m loosethread.case` prints a case sheet: an intro scene, case facts,
  people with impression and motive, a drawn map, the rules (DESIGN §3–4 in player words), evidence
  tagged with the slot it belongs to, and the testimony as a people × slot notebook grid (an "at" and
  a "with" row per person, surnames for company) with the theft window boxed in. A verdict prompt
  ends the player part; the truth uses the same grid with `*` for the theft and `!` for lies.
  Text wraps at 80 columns by display width (CJK = 2) and prefers breaks after punctuation.
- **Content pack**: new fields `intro`, `map_art` and `map_art_optional` (zh/en). The loader checks
  that the intro formats and that the drawing names exactly the locations present, with and without
  the optional ones; it cannot check that the drawn lines match the adjacency list, so map drawings
  stay a review item. The zh last-seen evidence text was shortened to fit one line.
- **Consequences**: case data is unchanged (same seeds, same facts); only the sheet text differs.
  English grids are about 110 columns wide. Alignment assumes a monospace font where CJK characters
  are exactly two columns wide; proportional fallback fonts may drift.

## D-017 — CP-4 approved: sub-agent review for cases 214 and 222

- **Date**: 2026-10-30 · **Type**: strategic (lowers a P1 exit criterion) · **Approved by owner**
  (chat: "批准 B")
- **Context**: `docs/CHANGE_PROPOSALS.md` CP-4. The owner solved case 213 by hand and judged that
  patient tabulation of the testimony finds the contradiction; 992/1000 cases need exactly one.
- **Decision**: for 214 and 222, one sub-agent per case with a fresh context and only the
  `-player.txt` text in its prompt, told to use no tools. It must give the culprit and a pair of
  items that cannot both be true, one a statement by the culprit. Pass = right culprit and the pair
  exposes one of the culprit's lies (checked against `-full.txt`); anything else fails and the
  owner solves that case.
- **Consequences**: human evidence on sheet readability comes from one case. "No tools" is an
  instruction, not an enforced sandbox. Readability, fun and variety ("do cases feel formulaic?")
  move to the P2 playability gate.

## D-018 — P2 plan approved, with the owner's choices

- **Date**: 2026-10-30 · **Type**: strategic (clarifies an exit criterion, sets a budget) ·
  **Approved by owner** (chat: "按建议开工")
- **Context**: start of P2. The plan was restated in ten lines with five decision points.
- **Decision**:
  1. Tone tags depend on public information only (kind of question, how often this person was
     asked), never on guilt or on whether a claim is a lie.
  2. Parser test set: Claude drafts and labels 150-200 zh/en questions; the owner spot-checks a
     random 30; the set is frozen before the first measurement and split into dev (~50, used to tune
     prompts) and test (~150, measured once). Reports say the set was drafted by an LLM.
  3. The provisional parser exit criterion (>= 85%) applies to the DeepSeek backend; local Qwen and
     the rule-based parser are reported alongside as comparisons.
  4. P2 spending cap: CNY 20 for API calls. Prices are read from DeepSeek's site into config, a
     pilot of about 10 questions is run and extrapolated before any full run, and work stops and
     is reported if the cap would be exceeded.
  5. CP-1 option C (simulated systematic player as a second difficulty metric) is done in P2.
  6. Branch `p2-npc-pipeline`; step 1 is the offline template backend and game loop (no key needed),
     step 2 the model backends and parser accuracy, step 3 the playtest.
- **Consequences**: the owner sets `DEEPSEEK_API_KEY` as a user environment variable before step 2;
  code only ever refers to the variable name.
## D-019 — P2 step 1: offline backends and the terminal game

- **Date**: 2026-10-30 · **Type**: tactical
- **Context**: P2 step 1 (D-018): a complete game with no API key, so the loop and the isolation
  tests exist before any model is called.
- **Decision**:
  - Contracts in `loosethread.npc`: `ParseRequest` (question, addressee, lexicon of public names),
    `ParseResult` (a query or a `ClarifyReason`), `LineRequest` (speaker card, `AllowedFacts`,
    public world, clarify reason, repeat flag), `LineResult`, `Usage`. Model backends build their
    prompts from these only; `lines.line_payload` is the JSON they may embed.
  - `loosethread.lexicon`: names, roles, generated forms (老周, 沈先生, Mr Zhou) and the content
    pack's new `aliases` field; an alias shared by two entities is dropped. Clock times in digits,
    Chinese (九点一刻) and English (half past eight); bare small hours are not times (一点 = "a bit").
  - `loosethread.parser.RuleParser`: the offline parser and the baseline for parser accuracy.
    Anything it cannot read becomes a free "please rephrase" with a reason (unclear, need a time,
    time outside the evening, two people named). `canonical_question` renders a query as a plain
    question; every in-scope query round-trips in zh and en (tested on two cases).
  - `loosethread.lines`: template lines in zh and en, and the post-check `unauthorised`: every
    person, place, item and clock time in a line must appear in its facts, its query or the
    speaker's persona. It cannot catch a wrong relation between allowed names, negations, or names
    the lexicon does not know.
  - Tone (D-018 item 1): out-of-scope questions get "evasive"; from the sixth question to the same
    person, "irritated"; otherwise "calm". "Nervous" is unused for now.
  - `loosethread.game.Game` is the only play-loop module that holds the truth. Fail closed: a parser
    that raises or returns a query for someone else or with unknown names gives a free rephrase; a
    writer that raises, returns nothing or fails the post-check is replaced by the template line;
    each turn records why. Out-of-scope questions parse successfully and cost 1 (DESIGN §7).
  - Notebook ids: statements `S1, S2, ...` in the order obtained, evidence keeps `E1...`. Hints list
    obtained pairs in direct conflict (solver rule), hidden with `--hard`.
  - Scoring (DESIGN §9): a pair "exposes a lie of the culprit" when the two items are in direct
    conflict and one of them is a false claim whose source is the culprit (hearsay counts for its
    source). Stars use `min_questions` from the P1 plan.
  - `python -m loosethread.play`: default case = today's date as the seed with the daily preset;
    `--lang`, `--hard`, `--budget`, `--log` (JSONL turns + summary, no credentials). Debug-CLI
    layout helpers became public (`render_sheet`, `render_notebook`, `render_truth`, `hang`, ...).
- **Observation (open)**: on 200 daily seeds, playing exactly the oracle question plan leaves no
  pair that exposes a lie of the culprit in 56/200 = 28.0% [Wilson 95%: 22.2%, 34.6%]: the plan
  rules the innocents out by elimination, and the player must ask more to attach a lie. So the
  ★★★ threshold (`min_questions` + 2) is tighter than it looks for those cases. To be measured with
  the simulated-player metric (CP-1 option C) in step 2 before proposing any change to scoring.
- **Consequences**: 159 tests pass (parser round trips, post-check on every template line, fail
  closed backends, every backend request equals the answer table's output on three cases).
  Recorded demos: `docs/review/p2/demo-213-zh.txt`, `demo-213-en.txt`.

## D-020 — P2 step 1: fixes from the owner's first offline playtest

- **Date**: 2026-10-31 · **Type**: tactical (parser fix) and owner-approved game changes (chat:
  "照建议改")
- **Context**: the owner played case 20261031 offline (log:
  `docs/review/p2/playtest-20261031-zh.jsonl`). Right culprit, but the accusation cited two items
  that do not conflict, so the result was a hunch (☆); 19 of 20 questions used, minimum 3. The
  hint for the exposing pair (S1/S5) had appeared at question 5. The 15 questions in one fixed
  pattern ("20:15-20:30 你在哪里？和谁在一起？") all parsed correctly; the 8 free-form ones were all
  misread, because the rule parser kept only the first clock time and ignored relative words.
  4 of them were charged (4 of the 19 questions used bought answers to questions not asked); the
  other 4 were taken as repeats of a different question.
- **Decision**:
  1. Parser (tactical, fail closed): every clock time in a question must fall in one slot. A range
     that names exactly one slot ("20:15–20:30") is that slot; anything wider gets the new reason
     `ONE_SLOT` (free), whose line also suggests "when were you there". A clock time next to a
     relative word (之后, 下一个, after, before, ...) gets `NEED_TIME`. More "with whom" phrases
     (身边, 其他人, beside you, ...). Replaying the 23 playtest inputs: 16 parse as intended, the
     other 7 now get a free rephrase, and none is charged for a misreading.
  2. Echo (approved): every answered or repeated question shows what it was read as, e.g.
     "→ 按“苏曼 20:15–20:30 在哪”记入笔记：S16", so a misreading is visible at once.
  3. Accusation (approved): in normal mode, if the two items are not among the contradiction
     hints, the confirmation says so first; hard mode does not warn. After a ☆ or ✗ the result
     names the notebook pairs that would have exposed the culprit's lie, or says there were none.
- **Not changed**: scoring, budget, question schema. Two observations go to the playability gate:
  the owner filled the whole window table, 5 suspects × 3 slots = 15 questions, which fits in the
  budget of 20 for this case, so the budget did not force choices (only the stars do); and
  "with whom" answers include the place, so "where" questions are never needed.
- **Consequences**: 174 tests pass; the playtest questions are parser regression tests; demos
  regenerated. The rule parser still cannot answer relative or multi-slot questions, it only
  refuses them for free; step 2 measures the LLM parser on such phrasings too.
## D-021 — P2 step 2 (part 1): model backends, question set draft, simulated player

- **Date**: 2026-10-31 · **Type**: tactical (within the plan approved in D-018)
- **Decision**:
  - `loosethread.llm` (optional extra): `backends.toml` names each backend's URL, model, key
    variable and prices (DeepSeek's zh pricing page, read 2026-10-31: `deepseek-flash` CNY 2 / 8
    and `deepseek-v4-pro` CNY 9 / 27 per 1M input / output tokens at peak; costs are computed at
    peak price with every input token a cache miss, so they are upper bounds). `OpenAIChat` lists
    the server's models before first use and refuses an unlisted name; the key is read from the
    named variable and never stored, printed or logged, and failures are recorded by exception
    type only. CI now installs the `llm` extra (tests use a fake model; no network).
  - `LLMParser`: prompt = public lexicon (names, aliases, slot times), addressee, question. The
    reply must be one JSON object; malformed JSON, an unknown kind, reason or id, a bad slot or an
    impossible shape raises `BackendError`, which the game turns into a free rephrase while
    keeping the usage. Time guard (default on): the deterministic clock reading
    (`parser.time_reading`) must agree with the model's slot.
  - `LLMWriter`: prompt = `lines.line_payload` and a system text in the target language; a reply
    cut off by the token limit falls back to the template line. `play.py --backend NAME`.
  - Parser question set (D-018 item 2): 199 items (119 zh, 80 en) on cases 213, 7 and 42,
    stratified into dev 51 / test 148; scoring rules fixed in `data/parser/README.md` before any
    measurement (accuracy pools clarify reasons; errors split into charged wrong / needless
    rephrase / invalid). `python -m loosethread.parser_eval` refuses an unfrozen set, measures the
    test split once per backend, and requires a DeepSeek pilot of at most 10 items with a projected
    total under CNY 20. Owner spot-check of 30 items: `docs/review/p2/parser-spotcheck.md`.
  - Simulated systematic player (D-018 item 5): `python -m loosethread.simulate`; results and the
    resulting proposal in CP-5. It answers the D-019 observation: for this player, an identified
    culprit without an exposing pair occurs in 339/4000 runs and costs 3.1 more questions on
    average, so that observation needs no change on its own.
  - `Game.exposes_culprit_lie` is public (scoring and the simulation read the truth through it;
    the terminal front end only after the accusation).
- **Smoke check, not a measurement**: the local Qwen2.5-7B (Q4_K_M, llama.cpp) answered end to end
  on case 0 with 8 questions outside the set: 3 parsed as intended; prompts are ~1,970 tokens;
  0.2–1.6 s per call. Prompt tuning waits for the frozen dev split.
- **Not done yet**: freezing the set (after the owner's spot-check), any accuracy measurement,
  any DeepSeek call (`DEEPSEEK_API_KEY` is not set).
## D-022 — Parser set frozen; rule and local-model accuracy measured

- **Date**: 2026-10-31 · **Type**: tactical (within D-018); results reported as measured
- **Spot-check and freeze**: the owner checked the 30 random items in
  `docs/review/p2/parser-spotcheck.md` and found no wrong label (chat: "全部正确"). 30/30 bounds
  the label error rate below 11.4% (Wilson 95% upper bound); it cannot rule out a few wrong labels
  among the other 169. `data/parser/questions.jsonl` is frozen at SHA-256
  `13e22acc0eaf413cfede733e6138169ccdb9e668fada5db0c14060b0ba57d60d`.
- **Harness**: dev runs are numbered rounds (all kept); the test split is measured once per
  backend; rows record a hash of the parser prompt.
- **Model parser, tuned on dev only** (local Qwen2.5-7B Q4_K_M, three rounds, then stopped):
  r1 35.3% (slot indices computed by the model were mostly wrong) → r2 74.5% (the model returns
  the clock time it read, code maps it to a slot; worked examples built from the case's own names,
  checked never to equal a set question; `{"clarify": "out_of_scope"}` read as that kind) → r3
  82.4% [69.7%, 90.4%] (`time: null` for where/with_whom read as "needs a time", ranges mapped in
  code, explicit rules for "when" and for roles).
- **Test split, measured once** (148 items; accuracy pools clarify reasons, see
  `data/parser/README.md`):

  | parser | accuracy | charged wrong | needless rephrase | invalid |
  |---|---|---|---|---|
  | rules | 132/148 = 89.2% [83.2%, 93.2%] | 8 | 8 | 0 |
  | local Qwen 7B, time guard | 114/148 = 77.0% [69.6%, 83.1%] | 16 | 14 | 4 |
  | local Qwen 7B, raw | 111/148 = 75.0% [67.5%, 81.3%] | 25 | 8 | 4 |

  Rules vs guarded Qwen on the same items: only rules right 26, only Qwen right 8, exact McNemar
  p = 0.003. The guard vs raw difference is not significant (5 vs 2, p = 0.45), but the guard
  removes 9 of 25 charged errors. Qwen drops from 82.4% on dev to 77.0% on test.
- **Negative result**: the local 7B parser is worse than the rule parser on this set and charges
  the player twice as often. Exploratory and post hoc (decided after seeing test): "rules first,
  model only when the rules ask to rephrase" scores the same 89.2% on test but turns 5 free
  rephrases into charged errors (8 → 13), so it is not adopted.
- **Caveat**: the rule parser and the question set have the same author (Claude). Although the set
  deliberately includes phrasings the rules cannot read, it may still favour them; the owner's
  playtest (8 free-form questions, all misread before D-020) is the only real-player sample.
- **Not done**: DeepSeek (the P2 criterion of >= 85% applies to it, D-018); `DEEPSEEK_API_KEY` is
  not set. If DeepSeek does not beat the rule parser, the parser design itself needs a CP.

## D-023 — CP-5 approved: stars graded against simulated systematic players

- **Date**: 2026-10-31 · **Type**: strategic (scoring, DESIGN §9) · **Approved by owner** (chat:
  "选 B")
- **Context**: CP-5. With the oracle-based rule, the median systematic run reached ★★★ in 0/200
  daily cases; the sweep of 15 questions fits the budget of 20 in every daily case.
- **Decision**: option B. Per case, 20 simulated systematic players (orders seeded `stars:0..19`,
  independent of the truth) set the thresholds: ★★★ ≤ their 25th percentile, ★★ ≤ their median,
  ★ otherwise, both capped at the budget. `game.StarRule`, `simulate.star_rule`; the game computes
  the rule once, at the accusation (0.2–1.1 s on the cases tried). The result screen shows this
  case's thresholds, or "any solve within the budget earns ★★★" when the 25th percentile is at
  or past the budget. Budget stays 20 (CP-3); option C (a budget that bites) is for the step 3
  playtest.
- **Observations, not changed** (from the 4,000 analysis runs, seeded differently from the game,
  so indicative): typical thresholds ★★★ ≤ 9, ★★ ≤ 12. In 34/200 cases the median simulated
  player needs more than 20 questions, so there any solve within the budget earns ★★★. In 1/200
  cases the new ★★★ threshold is below the old "minimum + 2", so a player who follows the oracle
  plan with two spare questions would get ★★ there.
- **Consequences**: case 213's demo now shows "any solve within 20 earns ★★★"; the owner's
  playtest case (20261031) has ★★★ ≤ 9, ★★ ≤ 12. Pre-CP-5 star rates stay reproducible from
  `simulate --score` (labelled "before CP-5").

## D-024 — DeepSeek pilot: thinking mode off; headline variant fixed before the test

- **Date**: 2026-10-31 · **Type**: tactical (backend settings, harness); the headline variant is
  stated before the DeepSeek test so it cannot be picked after
- **Pilot** (10 dev items, `parser-deepseek-dev-first10-r1`, CNY 0.051): 8/10 right, 2 invalid.
  Both were cut off: DeepSeek's thinking mode is on by default, its hidden reasoning tokens count
  against `max_tokens`, and the parser allows 120. A probe of one item with a larger budget used
  162 reasoning tokens, then answered correctly. The models list showed `deepseek-flash` and
  `deepseek-v4-pro`, as configured.
- **Change**: `backends.toml` gains `thinking` (sent as `{"thinking": {"type": ...}}`) and
  `reasoning_tokens` (added to every call's `max_tokens`). `deepseek` and `deepseek-pro` turn
  thinking off; `deepseek-think` turns it on with 1,024 extra tokens. A reply cut off by the
  token limit is now `too_long` in the parser and the harness (it was read as `not_json`); rows
  record the thinking setting.
- **Dev, 51 items** (same prompt as local r3, which was tuned on dev with Qwen, so dev is not a
  held-out estimate for any model):

  | backend | guarded | raw | completion tokens (median) | seconds (median) | CNY/question (max) |
  |---|---|---|---|---|---|
  | `deepseek` (thinking off) | 49/51 = 96.1% [86.8%, 98.9%] | 51/51 = 100% [93.0%, 100%] | 13 | 1.14 | 0.0046 |
  | `deepseek-think` | 49/51 = 96.1% [86.8%, 98.9%] | 51/51 = 100% [93.0%, 100%] | 44 | 1.40 | 0.0049 |

  No charged errors and no invalid replies in either. The guard's only effect was 2 needless
  rephrases ("差一刻九点…", "twenty to ten"), times the deterministic reader cannot read.
- **Decision**: `deepseek` (thinking off) is the DeepSeek backend for the game and for the test
  measurement: same dev accuracy, faster, and DeepSeek honours `temperature` only with thinking
  off. **The P2 criterion is judged on the guarded variant** (the parser as the game runs it);
  raw is reported alongside. Whether to drop the guard for DeepSeek is not decided from 2 dev
  items, and not from the test split.
- **Spend**: CNY 0.535 so far (upper bound: peak price, every input token a cache miss; DeepSeek
  reported most prompt tokens as cache hits). The test (148 items) projects about CNY 0.68 more.

## D-025 — DeepSeek parser measured on the test split: P2 parser criterion met

- **Date**: 2026-10-31 · **Type**: result (within D-018); measured once, as fixed in D-024
- **Test split, 148 items** (`results/rows/parser-deepseek-test.jsonl`; `deepseek-flash`,
  thinking off; owner's go-ahead in chat: "跑 test"):

  | parser | accuracy | charged wrong | needless rephrase | invalid |
  |---|---|---|---|---|
  | **DeepSeek, time guard (criterion)** | **138/148 = 93.2% [88.0%, 96.3%]** | 3 | 7 | 0 |
  | DeepSeek, raw | 143/148 = 96.6% [92.3%, 98.5%] | 3 | 2 | 0 |
  | rules (D-022) | 132/148 = 89.2% [83.2%, 93.2%] | 8 | 8 | 0 |
  | local Qwen 7B, time guard (D-022) | 114/148 = 77.0% [69.6%, 83.1%] | 16 | 14 | 4 |

  By language (guarded): zh 85/88 = 96.6% [90.5%, 98.8%], en 53/60 = 88.3% [77.8%, 94.2%].
- **Criterion**: ≥ 85% on DeepSeek is met; the whole Wilson interval is above it.
- **DeepSeek vs rules** (guarded, same items): only DeepSeek right 10, only rules right 4,
  exact McNemar p = 0.18. **Not a significant difference** at this sample size. Exploratory (not
  fixed in advance): charged errors 3 vs 8, paired 2 vs 7, p = 0.18, also not significant.
- **The guard**: 5 needless rephrases, 0 charged errors prevented (guard vs raw p = 0.0625). All 5
  are clock formats the deterministic reader cannot read ("21.30", "2045", "2030", "ten past
  nine", "九点过一刻"); the rule parser charges wrong answers on some of the same formats. Widening
  that reader would help both parsers, but these formats were found on the test split, so any
  gain must be measured on new questions or playtest data, not on this split.
- **DeepSeek's misses**: "嗯……" and "Hmm." read as small talk, which costs a question (expected
  "please rephrase"); "Where were you when the watch went missing?" read as out of scope
  (expected "name a time"; the rules make the same error); "你哪个时间段在厨房" and "Have you seen
  Shen Huaishan since dinner?" refused for free.
- **D-022 said** the parser design needs a CP if DeepSeek does not beat the rules. It is ahead
  but not significantly. No CP is proposed now: the criterion is met, both parsers ship (rules
  offline by default, DeepSeek with `--backend deepseek`), and which is the default is better
  judged from the step 3 playtest, where real players' phrasing is the open question (the rule
  parser misread all 8 of the owner's free-form questions before D-020).
- **Caveats**: the set and the rule parser have the same author (D-022); the prompt was tuned on
  dev with Qwen; DeepSeek replies are not guaranteed to be reproducible, but the rows are kept.
- **Spend**: CNY 1.214 in total (upper bound) of the CNY 20 cap; parsing costs at most CNY 0.0046
  and about 1.1 s per question.