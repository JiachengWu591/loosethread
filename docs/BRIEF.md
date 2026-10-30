# Project brief — 破绽 / Loose Thread

Source: the owner's project prompt (2026-10-29), sections 1–4. Changes since then are logged in
`DECISIONS.md` (name: D-001, theme: D-004).

## 1. Overview

- **Name**: 破绽 / Loose Thread (working name was 「不在场证明」/ Alibi, dropped after a name check — D-001).
  Package and import name: `loosethread`. Local folder: `E:\alibi`.
- **One line**: a Chinese-first, bilingual (zh/en) AI deduction game. The player interrogates suspects
  in natural language and finds the culprit through contradictions in their testimony. Every case is
  procedurally generated and proven uniquely solvable by a solver. NPC lines are spoken by an LLM, but
  the LLM is structurally unable to access the truth it must not reveal.

### Core mechanics

- **A case is a symbolic world model**: people, locations, time slots, items, motives, events,
  evidence. The truth lives only here.
- **The solver starts only from information available to the player** and verifies two things:
  exactly one suspect is consistent with all of it; and solving requires at least one contradiction
  inference (filters out trivial cases).
- **Lies are fixed by the generator**, not improvised in dialogue, so repeated questions get consistent
  answers. The culprit fakes an alibi; innocents may tell small lies for privacy. Every lie can be
  exposed by at least one piece of evidence or testimony.
- **NPC answers go through a three-stage pipeline**:
  1. parser LLM: turns the question into a structured query;
  2. program lookup + lie policy: computes the facts this answer is allowed to state;
  3. line LLM: receives only those facts and voices them in character.
- **Game layer**: a daily case with the same seed for everyone and a limited question budget; an
  automatic detective notebook with contradictions marked; accusations must cite evidence; a
  spoiler-free share card at the end.

## 2. Purpose (by priority)

1. **Research artifact** for master's applications (informatics / CE / data science) showing LLM
   systems engineering + security + evaluation. Thesis: *structural isolation, not prompt
   instructions, is what keeps LLM NPCs from both making things up and being talked into leaking.*
   Prove it with data, and report the costs.
2. **Shareable software**: fun, fast to pick up, shareable — to earn downloads and stars.
3. **Continue the owner's research line**: injection-blast-radius (architectural isolation against
   prompt injection) and zh-ipi-bench (Chinese indirect prompt injection benchmark), now applied to
   interactive entertainment.

**Non-goals**: 3D or big-budget art; online multiplayer; a general "AI murder-mystery platform";
monetization before Phase 5.

## 3. Audiences

- **Players**
  - Who: Chinese mystery fans (剧本杀, detective fiction, Wordle-style daily puzzles) and English
    players of AI games on itch.io.
  - Expect: learn in 5 minutes, a 10–20 minute session, results worth sharing.
- **Developers and researchers** interested in LLM NPC reliability, prompt injection and procedural
  narrative. Expect clean architecture, reproducible experiments, reusable modules.
- **Admissions reviewers**: within one minute of the README's first screen, understand the problem,
  method, evidence and limitations.

## 4. Competition and positioning

Checked 2026-10-29 by the owner and extended 2026-10-30; not exhaustive. Links and details:
`RELATED_WORK.md`.

- **Steam**: Vaudeville (left Early Access 2025-11; "Mixed", ~47% positive). Main complaints: the AI
  answers off-topic and goes off-script; some players say it became stiff after restrictions were
  tightened.
- **itch.io**: a cluster of LLM interrogation games (AI Noir, The Interrogator, Murder in Aisle 4, and
  others). The pages checked so far do not mention solvability checks or truth isolation.
- **Non-LLM daily deduction puzzles** (found 2026-10-30): Alibi Grid and Alibi — Spot the Lie already
  offer a daily case, cases solvable by logic, and (Alibi Grid) a spoiler-free emoji share grid. These
  features are therefore **not** a differentiator.
- **Non-LLM relatives**: Shadows of Doubt (procedural cases, no natural-language interrogation);
  Murdle (hand-made logic puzzles).
- The idea "keep the truth in a database, let the LLM only phrase it" has been suggested publicly, so
  **the idea itself is not new**.
- **Related research**: arXiv 2508.19288 (NPC secret leakage via prompt injection); arXiv 2310.16049
  MuSR (narrative reasoning data generation).
- **Positioning**: the difference is *having built it and measured it* — natural-language
  interrogation over a solver-verified world model, structural isolation with measured leakage and
  cost, Chinese-first, open source, reproducible evaluation.
- **Hard rule**: no "first / novel / 首个 / 唯一" claims in any file or public copy until
  `RELATED_WORK.md` has been re-searched.
