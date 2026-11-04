"""Serve the browser version on this machine.

python -m loosethread.web                 # assembles the site, serves http://127.0.0.1:8000
python -m loosethread.web --port 9000
python -m loosethread.web --host 0.0.0.0  # lets a phone on the same network try it

A page with a module worker and WebAssembly needs a server: a file:// page cannot load them. MIME
types are set here because `mimetypes` reads the Windows registry, which may call .js plain text.
"""

import argparse
import contextlib
from collections.abc import Sequence
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from os import PathLike
from pathlib import Path

from loosethread.web.build import build

_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".wasm": "application/wasm",
    ".json": "application/json",
    ".zip": "application/zip",
}


class _Handler(SimpleHTTPRequestHandler):
    def guess_type(self, path: str | PathLike[str]) -> str:
        return _TYPES.get(Path(path).suffix, "application/octet-stream")

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")  # a local server is for trying changes
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m loosethread.web", description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)
    site = build()  # every time, so that it cannot serve an old copy
    server = ThreadingHTTPServer((args.host, args.port), partial(_Handler, directory=str(site)))
    print(f"Loose Thread: http://{args.host}:{args.port}  (Ctrl-C to stop)", flush=True)
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
