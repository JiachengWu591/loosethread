# Roadmap

Living document. Status values: `planned` / `in progress` / `done` / `changed` / `dropped`.
All numeric thresholds are provisional and may only change through the process in `CLAUDE.md`
(strategic changes need an approved change proposal; exit criteria are never lowered silently).

| Phase | Title | Status |
|---|---|---|
| P0 | Skeleton and design | done |
| P1 | Case generator and solver | done |
| P2 | NPC pipeline and CLI playable | in progress |
| P3 | Evaluation study | planned |
| P4 | Web version, daily case, sharing | planned |
| P5 | Release v0.1.0 | planned |

Commands below use the package name `loosethread` (originally `alibi`; renamed by D-001).

---

## P0 — Skeleton and design · `done`

- **Goal**: turn the project prompt into long-lived repo docs and set up an empty project whose tests run.
- **Work**
  1. Environment self-check: python, uv, git versions, nvidia-smi. Report only; change no system settings.
  2. Name check: GitHub, itch.io, Steam, PyPI; give 2–3 alternatives.
  3. Project init: `git init`; `src/loosethread/`, `tests/`, `docs/`, `results/`, `assets/`; pyproject
     via uv with extras `llm`, `web`, `dev`; CI.
  4. Docs: `CLAUDE.md` (condensed §5–7 and §9), `docs/BRIEF.md` (§1–4), `docs/ROADMAP.md` (§8, with
     status), `docs/DECISIONS.md`, `docs/RELATED_WORK.md` (§4 with links).
  5. `docs/DESIGN.md` first draft: case theme; scale (e.g. 4–6 suspects, 5–8 locations, 6–10 time
     slots); question budget; win/loss and scoring.
  6. Data contracts first draft: Person, Location, TimeSlot, Item, Event, Fact, Statement, Evidence,
     Case, Query, AllowedFacts.
- **Exit criteria**: pytest, ruff, mypy all pass; CI is green; the owner has reviewed DESIGN.md.
- **Outcome (2026-10-30)**: items 1–6 done on branch `p0-skeleton`. Repo
  `github.com/JiachengWu591/loosethread`; CI green on ubuntu and windows. DESIGN.md reviewed; all
  open questions resolved as proposed (D-009). All exit criteria met.

## P1 — Case generator and solver · `done`

- **Goal**: for any seed, generate a case proven uniquely solvable by an independent solver, with
  controllable difficulty.
- **Work**
  1. Generate a ground-truth timeline under physical constraints: no being in two places at once;
     movement only between adjacent locations.
  2. Derive evidence from the truth, and each NPC's knowledge (witnessed / hearsay / unknown).
  3. Implement the lie policy, guaranteeing every lie has at least one exposing flaw.
  4. Solver: uses only player-available information — evidence and all possible statements
     (including lies); kept separate from generator code and never reads truth fields.
  5. Difficulty metrics: contradictions required, minimum questions, inference steps. Filter by
     difficulty at generation time.
  6. Content packs: people, locations, motives, items as zh/en data files, not hard-coded.
  7. Debug command `python -m loosethread.case --seed N`: prints the case as readable text,
     including the truth.
- **Exit criteria**
  - Unique-solvability rate 100% over 1,000 random seeds. Failing cases are rejected and regenerated;
    report the rejection rate.
  - Generation time < 1 s per case.
  - Property tests based on stdlib `random`.
  - ~~The owner reviews 3 cases by hand and can deduce the culprit.~~ **Changed by CP-4
    (2026-10-30, D-017):** the owner solves one review case by hand; for the other two, a fresh
    sub-agent given only the player sheet names the culprit and a pair of items that exposes one of
    the culprit's lies. If a sub-agent fails, the owner solves that case by hand.
- **Progress (2026-10-30, branch `p1-generator-solver`)**
  - Done: content pack + loader, generator, answer lookup, independent solver, audit, difficulty
    metrics, `python -m loosethread.case` (single case, `--hide-truth`, `--metrics`, `--batch N`).
  - 1,000 seeds, both contradiction rules: 1000/1000 audited unique + all guarantees
    [Wilson 95%: 99.6%, 100%]; rejection rate 35.5% (naive) / 81.5% (trusting); generation time max
    0.033 s / 0.220 s. Details in `docs/review/p1/batch-*.txt`.
  - Tests: brute-force cross-check of the solver, property tests on random seeds, determinism across
    `PYTHONHASHSEED`, AST isolation of solver and metrics.
  - CP-1, CP-2, CP-3 approved (D-015): trusting acceptance is the default; daily preset
    `generator.DAILY` (min questions 3–6) generates in ≤ 0.63 s on seeds 0–299.
  - Owner review: case 213 solved correctly, no problems found; the sheet was "too rigid", so the
    debug CLI now prints a case-sheet layout (D-016).
- **Outcome (2026-10-30)**: cases 214 and 222 solved by fresh sub-agents with valid accusation
  pairs under CP-4 (`docs/review/p1/REVIEW.md`, which also reports case variety over 1,000 seeds).
  All exit criteria met, the review criterion as changed by CP-4.

## P2 — NPC pipeline and CLI playable · `in progress`

- **Goal**: play one full case in the terminal in Chinese and one in English.
- **Work**
  1. Query schema: where, when, with whom, saw whom, about an item, opinion of someone, small talk,
     out of scope.
  2. Parser LLM: sees only character, location and item names plus the raw question; outputs validated
     JSON. On validation failure the NPC asks for clarification.
  3. Lookup + lie policy → `AllowedFacts`. Isolation holds at the type level: the line-prompt builder
     accepts only `AllowedFacts`.
  4. Line LLM: input is persona, `AllowedFacts` and an optional tone tag (nervous, evasive…), never the
     truth. Post-check: every entity in the line must be in `AllowedFacts` or the persona, else fall
     back to a template line.
  5. Three backends: DeepSeek, local llama.cpp, deterministic template backend (offline tests and
     key-free play).
  6. Game loop: question budget; automatic notebook (structured "who said whom was where when");
     contradiction hints; accusation with evidence; scoring.
  7. Log tokens, latency and cost per session; never the key.
  8. Isolation tests: intercept every prompt sent to an LLM; assert it contains no culprit marker and
     no unauthorized true fact.
  9. Parser accuracy: 150–200 hand-labelled zh/en questions; report accuracy with a Wilson interval.
- **Exit criteria**
  - The owner plays one case through in Chinese and one in English in the CLI.
  - All offline tests pass.
  - Parser accuracy ≥ 85% (provisional); if not reached, submit a change proposal.
- **Playability gate**: after P2, a playtest review with the owner and ideally 2–3 friends: "is it fun,
  where do you get stuck?" — and, added by CP-4, "do cases feel formulaic?" (99.2% of cases need
  exactly one contradiction). If not fun, iterate on P1/P2 before entering P3.
- **Plan approved 2026-10-30 (D-018)**: tone from public information only; LLM-drafted parser test
  set, owner spot-checks 30, frozen before measuring (dev ~50 / test ~150); the 85% criterion
  applies to DeepSeek; API spending cap CNY 20; CP-1 option C done in P2. Steps: (1) offline backends
  and game loop, (2) model backends and parser accuracy, (3) playtest.
- **Progress (2026-10-30, branch `p2-npc-pipeline`)**
  - Step 1 done (D-019): `python -m loosethread.play` plays a full case offline in zh and en with
    the rule-based parser and template lines; work items 1, 3, 6 and the offline half of 4, 5, 7, 8
    are in place. Isolation tests record every backend request on three cases and check it equals
    the answer table's output. Demos in `docs/review/p2/`.
  - Open: on 200 daily seeds, the oracle plan alone leaves no lie-exposing pair in 28.0%
    [22.2%, 34.6%] of cases (elimination instead of contradiction); to be measured with the
    simulated player in step 2 before any scoring change is proposed.
  - Owner's offline playtest 1 (2026-10-31, D-020): right culprit, but the cited pair did not
    conflict (☆, 19/20 questions). All 8 free-form questions were misread by the rule parser and
    4 were charged; fixed fail-closed (one slot per question, relative times refused). Answers now
    echo how the question was read; the accusation warns about a pair that is not a contradiction.
  - Step 2 part 1 (2026-10-31, D-021): DeepSeek and llama.cpp backends (fail closed, model list
    checked before use, costs as upper bounds); parser question set drafted (199 items, scoring
    fixed in `data/parser/README.md`), waiting for the owner's 30-item spot-check before freezing;
    evaluation harness with the spending guardrails; simulated-player metric done, which led to
    CP-5 (open): a methodical sweep fits the budget in every daily case and never earns ★★★.
  - Step 2 part 2 (2026-10-31, D-022): set frozen after the owner's spot-check (30/30). Test
    split: rules 89.2% [83.2%, 93.2%]; local Qwen 7B (prompt tuned on dev, 3 rounds) 77.0%
    [69.6%, 83.1%], significantly worse than rules (McNemar p = 0.003) and charging twice as
    many wrong answers: a negative result for the local model.
  - CP-5 approved (D-023): stars are graded per case against 20 simulated systematic players
    (★★★ ≤ their fastest quarter, ★★ ≤ their median); budget stays 20.
  - DeepSeek pilot (D-024): thinking mode (on by default) cut off 2 of 10 replies; with it off,
    dev is 96.1% [86.8%, 98.9%] guarded, 100% raw, 1.1 s per question; thinking on is no more
    accurate and slower. The criterion is judged on the guarded variant. Spent CNY 0.54 of 20.
  - Next: DeepSeek test split (once, about CNY 0.68), compared with rules; then the playtest.

## P3 — Evaluation study · `planned`

- **Goal**: answer three research questions with data, as a reproducible report.
- **Pre-registration first**: `docs/STUDY_PLAN.md` (questions, hypotheses, metrics, sample sizes,
  analysis, stopping rules). Experiments start only after owner approval.
- **RQ1 Solvability**: an LLM writes cases in one shot (DeepSeek required, local Qwen optional);
  transcribe into the same schema and run the solver. Report shares of unique / multiple / no
  solution / self-contradictory. Control: this project's generator. Report transcription error.
- **RQ2 Consistency**: baseline = prompt-only NPC (whole case in the system prompt, told not to leak or
  make things up); treatment = layered pipeline. Same scripted interrogations; extract structured
  assertions from each line; check them against truth, lie policy and prior dialogue.
- **RQ3 Extraction resistance**: zh/en attack set — direct asks, role-play, instruction override,
  indirect injection via forged "evidence", encoding/paraphrase. Goal: make the NPC reveal the culprit
  or unauthorized facts. Judging: exact match + LLM judge; human spot-check on disagreement.
- **Costs must be reported alongside**: valid-answer rate on legitimate questions, tokens per session,
  latency — no "winning by refusing".
- **Sample size**: Wilson half-width ≤ ±7 pp ⇒ ~200 per condition. Pilot 10 items first to estimate
  cost; report the budget to the owner before the full run.
- **Deliverables**: `results/rows/`, `results/*.md`, `loosethread.verify`, `docs/REPORT.md` (with
  limitations), one results figure.
- **Exit criteria**: `verify` reproduces every table offline; the report states what the results do
  and do not show.

## P4 — Web version, daily case, sharing · `planned`

- **ADR first — architecture**: (a) Python backend + light frontend; (b) in-browser, bring-your-own
  key; (c) other. Compare cost, privacy, deployment, maintenance.
- **ADR — hosting mode**: BYO key / hosted demo / both. A hosted demo must have a daily token cap, rate
  limiting and a one-switch kill.
- **Features**: date → seed (time zone in the ADR); notebook UI; zh/en toggle; mobile layout;
  spoiler-free share card (emoji text grid, optional image).
- **Test assertions**: the share card contains no answer; the key never appears in frontend logs, URLs
  or shared content.
- **Exit criteria**: a full session playable in a local browser; per-session cost measured; the owner
  signs off on the feel.

## P5 — Release v0.1.0 · `planned`

- **Work**: bilingual README (first-screen GIF, one-command run, problem–method–evidence–limitations);
  LICENSE with code and content licenses explained separately — **vendor the full CC BY 4.0 legal
  code** (added 2026-10-30, see D-003); CHANGELOG and CITATION.cff; privacy note (what is sent to model
  providers); itch.io page copy and screenshots, release notes; re-run the RELATED_WORK search and the
  name check before release.
- **Optional**: desktop packaging (PyInstaller, Tauri, …; ADR first).
- **Exit criteria**: runs from the README in a clean environment; upload checklist handed to the owner.
