# Changelog

## 0.1.0

The first release.

### The game

- Interrogate suspects in natural language, in Chinese or English, and name the culprit with two records that cannot both be true.
- A new case each day, by your own local date. Three settings and four shapes of lie. A solver checks that each case has exactly one solution
  and needs a contradiction to solve.
- A notebook that fills itself in, with contradiction hints, and a hard mode that turns them off.
- A share card with no answer in it.

### Where it runs

- In a browser, with nothing to install and no key: rules read the questions and templates say the lines.
- With a DeepSeek key of your own, a model does both. The key stays in the page's memory. See `docs/PRIVACY.md`.
- In a terminal: `uv run python -m loosethread.play`.

### The evaluation

- A registered study of the layered pipeline against a hardened prompt, with raw rows and `python -m loosethread.verify` to recompute
  every table offline. See `docs/REPORT.md`, which reports what failed as well as what held.

### Known limits

- With no key, the lines are plain templates and no model is involved.
- In about half of cases, a hint on one person's own two answers names the culprit. Hard mode exists for this.
- The date is each player's own, so people in different time zones can be on different cases. The case number is on the page and the share card.
- No stranger had played it before this release.
