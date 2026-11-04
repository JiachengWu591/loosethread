"""The built site's Pyodide gives the same cases and games as CPython.

It needs node and a built site, so it is skipped on a machine without them, and CI asks for it with
LOOSETHREAD_WEB_CHECK=1, which turns a missing site into a failure. It runs the real runtime and
package, without a browser: it cannot see the page, the worker or anything else in `web/site`.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import loosethread
from loosethread.game import DEFAULT_BUDGET
from loosethread.llm.config import load_backends
from loosethread.model import Lang
from loosethread.web import bridge
from loosethread.web.build import BUNDLE, OUT
from loosethread.web.session import WebSession

HERE = Path(__file__).parent
REQUIRED = os.environ.get("LOOSETHREAD_WEB_CHECK") == "1"
READY = shutil.which("node") is not None and (OUT / BUNDLE).exists()
FAKE_KEY = "sk-this-is-a-fake-key-for-tests"


def _page_replies() -> dict[str, object]:
    """What the worker would say to the page over one game, from the real bridge."""
    seed = next(s for s in range(20261104, 20261154) if _a_sweep_exposes(s))
    culprit = WebSession(seed, Lang.ZH).game.case.truth.culprit
    start = bridge.start(seed, "zh", "")
    state = json.loads(start)["state"]
    names = {p["id"]: p["name"] for p in state["sheet"]["people"]}
    hard, normal = bridge.set_hints(False), bridge.set_hints(True)
    asked = _sweep(seed)
    current = bridge._current()
    pair = next(
        p for p in current.game.notebook.conflicts() if current.game.exposes_culprit_lie(*p)
    )
    evidence = current.game.case.view.evidence
    no_conflict = bridge.check(culprit, evidence[0].id, evidence[1].id)
    conflict = bridge.check(culprit, *pair)
    set_en, set_zh = bridge.set_lang("en"), bridge.set_lang("zh")
    accused = bridge.accuse(culprit, *pair)
    ending = json.loads(accused)["state"]["ending"]["lines"][0]
    listed = json.dumps({"data": [{"id": load_backends()["deepseek"].model}]})
    connected = bridge.connect(FAKE_KEY, lambda *_: (200, listed))
    refused = bridge.connect(FAKE_KEY, lambda *_: (401, "no"))
    left = bridge.disconnect()
    return {
        "start": [start],
        "set_hints": [hard, normal],
        "set_lang": [set_en, set_zh],
        "ask": [asked],
        "check": [no_conflict, conflict],
        "accuse": [accused],
        "connect": [refused, connected],
        "disconnect": [left],
        "suspect": [names[culprit]],
        "items": [[evidence[0].id, evidence[1].id]],
        "ending": [ending],
    }


def _questions(seed: int) -> list[tuple[str, str]]:
    view = WebSession(seed, Lang.ZH).game.case.view
    return [
        (str(person), f"{view.world.slots[slot].label.split('–')[0]} 你在哪？")
        for slot in view.crime.window
        for person in sorted(view.suspects)
    ][:DEFAULT_BUDGET]


def _sweep(seed: int) -> str:
    """Asks the questions through the bridge and returns the last reply, which has the state."""
    last = ""
    for person, text in _questions(seed):
        last = bridge.ask(person, text)
    return last


def _a_sweep_exposes(seed: int) -> bool:
    session = WebSession(seed, Lang.ZH)
    for person, text in _questions(seed):
        session.ask(person, text)
    game = session.game
    return any(game.exposes_culprit_lie(*p) for p in game.notebook.conflicts())


@pytest.mark.skipif(not REQUIRED and shutil.which("node") is None, reason="needs node")
def test_the_page_draws_a_whole_game_with_nothing_stray_on_screen(tmp_path: Path) -> None:
    """It reads the page's code and not a browser's work, so it cannot see layout or a real worker.
    Found by hand first (D-046): a stray null, and facts shown as [object HTMLElement]."""
    node = shutil.which("node")
    assert node is not None
    data = tmp_path / "replies.json"
    data.write_text(
        json.dumps({"replies": _page_replies(), "key": FAKE_KEY}, ensure_ascii=False),
        encoding="utf-8",
    )
    app = Path(loosethread.__file__).parent / "web" / "site" / "app.js"
    run = subprocess.run(
        [node, str(HERE / "web_page.mjs"), str(app), str(data)],
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr[-2000:]
    report = json.loads(run.stdout)
    assert report["problems"] == []
    assert report["hardKept"]
    assert report["hardReleased"]
    assert report["sawEnding"]
    assert not report["keyInStorage"]
    assert not report["keyOnScreen"]
    assert report["clearedAfterRefusal"]
    assert report["clearedAfterConnect"]
    assert report["keySentOnlyToConnect"]
    assert report["ops"] == [
        "accuse",
        "ask",
        "check",
        "connect",
        "disconnect",
        "set_hints",
        "set_lang",
        "start",
    ]


@pytest.mark.skipif(not REQUIRED and not READY, reason="needs node and a built site")
def test_the_browser_build_gives_the_same_cases_and_games() -> None:
    node = shutil.which("node")
    assert node is not None
    assert (OUT / BUNDLE).exists(), "run python -m loosethread.web.build first"
    browser = subprocess.run(
        [node, str(HERE / "web_node.mjs"), str(OUT), str(HERE / "web_digests.py")],
        capture_output=True,
        encoding="utf-8",
        check=True,
        timeout=600,
    )
    local = subprocess.run(
        [sys.executable, "-c", "import web_digests; print(web_digests.digests())"],
        capture_output=True,
        encoding="utf-8",
        check=True,
        cwd=HERE,
        timeout=600,
    )
    theirs, ours = json.loads(browser.stdout.splitlines()[-1]), json.loads(local.stdout)
    assert len(ours) == 50
    assert theirs == ours
