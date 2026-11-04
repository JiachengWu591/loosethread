"""Runs what the README tells a newcomer to run, with no extras installed.

CI runs it in a job of its own on a fresh machine (the exit criterion of roadmap P5). It shows that
the README's commands work and that the site serves what a browser asks for, with the right types.
It cannot show that a browser then plays the game; `tests/web_page.mjs` and a person do that.
"""

import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8765
SITE_TYPES = {
    "/": "text/html",
    "/app.js": "text/javascript",
    "/worker.mjs": "text/javascript",
    "/style.css": "text/css",
    "/NOTICES.txt": "text/plain",
    "/licenses/MPL-2.0.txt": "text/plain",
    "/loosethread.zip": "application/zip",
    "/pyodide/pyodide.mjs": "text/javascript",
    "/pyodide/pyodide.asm.mjs": "text/javascript",
    "/pyodide/pyodide.asm.wasm": "application/wasm",
    "/pyodide/python_stdlib.zip": "application/zip",
    "/pyodide/pyodide-lock.json": "application/json",
}
STARTUP_SECONDS = 300  # the first run fetches the runtime


def _commands() -> list[str]:
    """Each line of the README's bash blocks."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```bash\n(.*?)```", text, re.DOTALL)
    return [line.strip() for block in blocks for line in block.splitlines() if line.strip()]


def _serve_and_fetch(command: list[str]) -> None:
    server = subprocess.Popen(
        [*command, "--port", str(PORT)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=sys.platform != "win32",
    )
    try:
        deadline = time.monotonic() + STARTUP_SECONDS
        while True:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=5).close()
                break
            except OSError:
                if server.poll() is not None or time.monotonic() > deadline:
                    raise SystemExit("the site did not come up") from None
                time.sleep(1)
        for path, kind in SITE_TYPES.items():
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=30) as reply:
                got = reply.headers.get_content_type()
                size = len(reply.read())
            if got != kind or not size:
                raise SystemExit(f"{path}: type {got}, {size} bytes; expected {kind}")
            print(f"  {path}: {got}, {size} bytes")
    finally:
        # `uv run` starts Python as a child, and stopping only uv can leave that child serving.
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(server.pid)],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(server.pid, signal.SIGTERM)
        server.wait(timeout=30)


def _run(command: list[str], stdin: str = "", expect: str = "") -> None:
    done = subprocess.run(
        command,
        cwd=ROOT,
        input=stdin,
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
        timeout=600,
    )
    if done.returncode != 0 or expect not in done.stdout:
        print(done.stdout[-2000:], done.stderr[-2000:], sep="\n")
        raise SystemExit(f"{' '.join(command)} failed with exit code {done.returncode}")


def main() -> int:
    commands = _commands()
    print("README commands:", *commands, sep="\n  ")
    web = "uv run python -m loosethread.web"
    play = "uv run python -m loosethread.play"
    verify = "uv run python -m loosethread.verify"
    for needed in (web, play, verify):
        if needed not in commands:
            raise SystemExit(f"the README does not give: {needed}")
    print(web)
    _serve_and_fetch(web.split())
    print(play)
    _run(play.split(), "/q\ny\n", "破绽")
    print(verify)
    _run(verify.split(), expect="same")
    print("It all ran.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
