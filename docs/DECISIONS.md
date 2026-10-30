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
