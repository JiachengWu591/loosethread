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

from loosethread.web.build import BUNDLE, OUT

HERE = Path(__file__).parent
REQUIRED = os.environ.get("LOOSETHREAD_WEB_CHECK") == "1"
READY = shutil.which("node") is not None and (OUT / BUNDLE).exists()


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
