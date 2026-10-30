# results/

- `rows/` — raw experiment rows, one record per line (JSONL, UTF-8, LF), committed as produced.
- `*.md` — tables derived from `rows/`. Every table here must be re-computable offline, without
  API keys, by `python -m loosethread.verify` (added in Phase 3).

License: CC BY 4.0 (see `LICENSE-CONTENT.md`).
