"""The browser version (P4, CP-11): this package, run by Pyodide in a worker, under a static page.

`session` is one game as data for a page, `bridge` is what the page's worker calls, `share` writes
the spoiler-free card, and `browser_chat` reaches a model with a key of the player's own. `build`
assembles the site and `python -m loosethread.web` serves it locally. Nothing here needs a
third-party package.
"""
