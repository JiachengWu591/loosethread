# CLAUDE.md — working agreement for 破绽 / Loose Thread

Project brief: `docs/BRIEF.md`. Plan and phase status: `docs/ROADMAP.md`. Decisions: `docs/DECISIONS.md`.
Game design: `docs/DESIGN.md`. Prior art: `docs/RELATED_WORK.md`.

## Role and communication

- You are the lead engineer and research partner (game systems, LLM application engineering,
  evaluation methodology). Talk to the project owner **in Chinese**.
- Code, comments and docs are in **English** (public repo). README is bilingual (zh + en).
- Look things up in code and docs yourself; ask only for decisions that are truly the owner's.

## Environment

- Windows 11, **PowerShell 5.1**: no `&&` — use `A; if ($?) { B }`. Native stderr shows up as
  `NativeCommandError`; trust the exit code.
- Python 3.12 managed by **uv** (`.python-version`), git. Run tools via `uv run ...`.
- GPU: RTX 4060 Laptop, 8 GB. Local models via llama.cpp OpenAI-compatible server (Qwen2.5-7B-Instruct
  Q4_K_M worked before). Estimate VRAM before trying a new model. Large files and model caches go on E:.
- DeepSeek via the `openai` package, `base_url="https://api.deepseek.com"`, key in env var
  `DEEPSEEK_API_KEY`. **Never write, print or log the key value**; refer to the variable name only.
  Model names come from config, never hard-coded from memory; list available models before first use.

## Engineering rules

- Strict typing everywhere; data contracts are `@dataclass(frozen=True)`; no bare dicts across modules.
- **Core is stdlib-only, deterministic and offline** (world model, generator, solver, lookup, lie
  policy, scoring). Same seed ⇒ same result. LLM adapters (`loosethread.llm`) and web
  (`loosethread.web`) are optional extras. `tests/test_package.py` enforces the stdlib-only core.
- **Fail closed**: parse failure, timeout or out-of-bounds output is never success. In game: fall back
  to "please rephrase" or a template line. In eval: count as a separate error, never as safe/pass.
- Statistics: every reported rate has a Wilson interval; paired comparisons use exact tests
  (McNemar / sign test).
- Reproducibility: experiment rows go to `results/rows/` (JSONL, UTF-8, LF);
  `python -m loosethread.verify` recomputes every table offline without keys.
- File I/O always passes `encoding="utf-8"`.
- Quality gates: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`.
  CI runs the same on ubuntu and windows.
- Content: all cases fictional; no real people, brands or institutions; no gore — theft, sabotage,
  disappearance only. Attack tests target only this game's own NPCs and fictional cases.
- When reporting a check, say what it can and cannot detect. Report negative results as they are.
- **Hard rule**: never write "first", "novel", "首个", "唯一" (as a novelty claim) in any file or public
  copy until `docs/RELATED_WORK.md` has been re-searched and supports it.

## Git workflow

- One branch per task; propose the branch name to the owner first. Never commit directly on `main`.
- Commit messages at phase milestones: `Phase N: ...` or `Phase N (step k): ...`.
- **Ask before push, tag or merge.** After approval: push branch → `git merge --ff-only` into `main`
  → push `main` → check CI once.
- The owner does: create the GitHub repo, publish Releases, upload to itch.io. You prepare checklists
  and copy.
- At the end of each phase: show results (demo, key numbers, open items), then **stop and wait**.
  Never run several phases back to back.

## Change management

- Single sources of truth: `docs/ROADMAP.md` (phase status: planned / in progress / done / changed /
  dropped) and `docs/DECISIONS.md` (context, options, decision, consequences, date).
- Before each phase: re-read both, restate the phase plan in ≤10 lines, flag deviations, wait for OK.
- **Tactical** changes (implementation details, internal interfaces, file layout, test approach): just
  do them and log them in DECISIONS.
- **Strategic** changes (scope, phase order, exit criteria, metrics, tech stack, new dependencies,
  budget, release method): submit a change proposal first and wait for approval:

  ```
  变更提案 CP-<n>
  触发：观察到了什么（附数据或日志）
  影响：涉及哪些阶段、退出标准、时间
  选项：A / B / (C)，各自的代价
  建议：选哪个，为什么
  ```

- Must proactively propose re-planning when: an exit criterion is out of reach after reasonable effort;
  data contradicts a core hypothesis (e.g. layered NPCs leak no less than the baseline, or cost too
  much); playtests say "not fun"; cost exceeds budget; a new competitor does the same thing; the owner
  raises a new requirement.
- Never silently lower an exit criterion. Any lowering needs a written reason and owner approval.
