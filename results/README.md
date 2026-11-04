# results/

- `rows/` — raw experiment rows, one record per line (JSONL, UTF-8, LF), committed as produced.
- `*.md`, `figure.svg` — tables and the figure derived from `rows/`. Every one is recomputed offline, with no API key,
  by `python -m loosethread.verify`, which exits 1 on any difference.

Start with `docs/REPORT.md`, which says what these results do and do not show.

| File | What it holds |
|---|---|
| `hypotheses.md` | H1 to H5 against the numbers |
| `rq1.md` | One-shot cases, and the generator as control |
| `rq2.md` | Consistency, valid answers, costs, by group, and the post-hoc lines |
| `rq3.md`, `adaptive.md` | Static attacks and adaptive campaigns |
| `rq3-unhardened.md`, `judge-check.md` | Post-hoc controls for the attacks and for the judge |
| `repeat.md` | Run-to-run stability |
| `owner-checks.md` | The reviews and the blind rating, and who did each |
| `spend.md` | Study spending, upper bound |
| `parser.md`, `simulated-player.md` | Results from earlier phases |
| `lines-check.md`, `web-cost.md` | P4: the lines before and after CP-12, and what a game costs with a model |

License: CC BY 4.0 (see `LICENSE-CONTENT.md`).
