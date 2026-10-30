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
