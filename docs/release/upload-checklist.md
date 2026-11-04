# Release checklist for v0.1.0

For the owner. Steps marked **Claude** are mine, and each waits for your OK. The rest need your accounts.

## 1. Put a test version online

- [ ] **Claude**, after your OK: merge `p5-release` into `main`. The Pages workflow can only be run by hand once it is on `main`.
- [ ] GitHub → Settings → Pages → Build and deployment → Source: **GitHub Actions**.
- [ ] GitHub → Actions → **Pages** → Run workflow, on `main`.
- [ ] Open https://jiachengwu591.github.io/loosethread/ and see that it loads.

## 2. Three checks only you can do

Tell me what you find. If something fails, it gets fixed before the tag.

- [ ] **A valid key in a real browser.** Use a key with a spending limit. Click 用模型, enter it, and ask a few questions. Expect natural lines, a cost shown at the top, and no error. Refresh, and it should ask for the key again.
- [ ] **A real phone.** Open the link, or run `uv run python -m loosethread.web --host 0.0.0.0` and open your computer's LAN address. Play a few questions, open the notebook, and refresh. Check that nothing is cut off.
- [ ] **From mainland China**, without a VPN. Does the page load, and how long does the first load take? If it is unstable, tell me, and the itch.io copy and README should say so.

## 3. Name

- [ ] Search USPTO TSDR, EUIPO and CNIPA for "Loose Thread" and "破绽" (D-050). This is your call, and no legal opinion comes with this list. I recommend keeping the name unless something covers games.

## 4. Tag

- [ ] **Claude**, after your OK: set the date in `CHANGELOG.md` and `CITATION.cff`, and create and push the tag `v0.1.0`.
- [ ] GitHub → Settings → Environments → **github-pages** → Deployment branches and tags: add the tag rule `v*`. Do this before the tag, or the tag's deployment is refused. If it is, run the workflow by hand on `main`, as in step 1.

## 5. GitHub Release

- [ ] **Claude** builds the zip: `uv run python -m loosethread.web.build --zip` writes `dist/loosethread-web.zip`, about 6.2 MiB.
- [ ] GitHub → Releases → Draft a new release → tag `v0.1.0`. Paste `docs/release/release-notes-v0.1.0.md`. Attach the zip. Publish.

## 6. itch.io

- [ ] Create a new project, as a **Draft**, with the fields in `docs/release/itch-page.md`.
- [ ] Upload `loosethread-web.zip`. Tick **This file will be played in the browser**.
- [ ] Embed options: click to launch in fullscreen off; viewport 1024 × 768; **Mobile friendly** on; **Fullscreen button** on. Leave SharedArrayBuffer support off.
- [ ] Open the draft's page and play a few questions. Try a key too, if you are willing to enter one there: itch.io serves many games from one web address, so prefer a spending-limited key.
- [ ] Answer the AI disclosure, add the screenshots and cover, and set the page to **Public**.

## 7. Repository page

- [ ] GitHub → the repository's About: Website `https://jiachengwu591.github.io/loosethread/`. Topics: `llm`, `prompt-injection`, `game`, `deduction`, `procedural-generation`, `pyodide`.

## 8. After

- [ ] Tell me the itch.io link, and I will add it to the README.
- [ ] If you let a few friends play, what they say answers the questions D-048 left open.
