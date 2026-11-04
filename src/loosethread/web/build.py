"""Assembles the static site: the page, this package as a zip, and the Pyodide runtime.

python -m loosethread.web.build            # writes dist/web
python -m loosethread.web.build --zip      # and dist/loosethread-web.zip, to upload to itch.io

The runtime is fetched once at a pinned version, checked against its hash, and cached in build/. It
is not committed. A wrong hash stops the build. Pyodide is under MPL-2.0, for P5's LICENSE work.
"""

import argparse
import hashlib
import shutil
import tarfile
import urllib.request
import zipfile
from collections.abc import Sequence
from pathlib import Path

PYODIDE_VERSION = "314.0.7"
PYODIDE_ARCHIVE = f"pyodide-core-{PYODIDE_VERSION}.tar.bz2"
PYODIDE_URL = (
    f"https://github.com/pyodide/pyodide/releases/download/{PYODIDE_VERSION}/{PYODIDE_ARCHIVE}"
)
PYODIDE_SHA256 = "2abdcc2e35208af406e07724cffa85bc582ced97e9028383ecf5462541393f95"
# All a page needs to start Pyodide (https://pyodide.org/en/stable/usage/downloading-and-deploying.html).
RUNTIME_FILES = (
    "pyodide.mjs",
    "pyodide.asm.mjs",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
    "pyodide-lock.json",
)
PACKAGE = Path(__file__).resolve().parent.parent
SITE = Path(__file__).resolve().parent / "site"
CACHE = Path("build") / "pyodide"
OUT = Path("dist") / "web"
BUNDLE = "loosethread.zip"
# What a browser never runs: the study, tools for the terminal, and the client that needs `openai`.
_LEFT_OUT_DIRS = frozenset({"study", "site", "__pycache__"})
_LEFT_OUT_FILES = frozenset(
    {
        "verify.py",
        "parser_eval.py",
        "llm/client.py",
        "web/build.py",
        "web/__main__.py",
        "py.typed",
    }
)


def bundled_files() -> list[tuple[Path, str]]:
    """Each file of the package that goes to the browser, with its name in the zip."""
    files = []
    for path in sorted(PACKAGE.rglob("*")):
        rel = path.relative_to(PACKAGE)
        if path.is_dir() or _LEFT_OUT_DIRS & set(rel.parts) or rel.as_posix() in _LEFT_OUT_FILES:
            continue
        files.append((path, f"loosethread/{rel.as_posix()}"))
    return files


def pack_package(target: Path) -> None:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path, name in bundled_files():
            info = zipfile.ZipInfo(
                name, date_time=(2026, 1, 1, 0, 0, 0)
            )  # same bytes on every build
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, path.read_bytes())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_runtime(cache: Path = CACHE) -> Path:
    """The runtime's folder, downloaded if needed. Raises if the archive is not the pinned one."""
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / PYODIDE_ARCHIVE
    if not archive.exists() or _sha256(archive) != PYODIDE_SHA256:
        print(f"fetching {PYODIDE_URL}")
        with urllib.request.urlopen(PYODIDE_URL, timeout=120) as reply:
            archive.write_bytes(reply.read())
    if (found := _sha256(archive)) != PYODIDE_SHA256:
        archive.unlink()
        raise RuntimeError(f"{PYODIDE_ARCHIVE} has hash {found}, expected {PYODIDE_SHA256}")
    folder = cache / PYODIDE_VERSION
    if not all((folder / name).exists() for name in RUNTIME_FILES):
        folder.mkdir(exist_ok=True)
        with tarfile.open(archive, "r:bz2") as tar:
            for name in RUNTIME_FILES:
                member = tar.extractfile(f"pyodide/{name}")
                if member is None:
                    raise RuntimeError(f"{PYODIDE_ARCHIVE} lacks {name}")
                (folder / name).write_bytes(member.read())
    return folder


def build(out: Path = OUT, cache: Path = CACHE) -> Path:
    runtime = fetch_runtime(cache)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SITE, out)
    (out / "pyodide").mkdir()
    for name in RUNTIME_FILES:
        shutil.copy(runtime / name, out / "pyodide" / name)
    pack_package(out / BUNDLE)
    return out


def zip_site(site: Path, target: Path) -> None:
    """index.html at the root of the zip, as itch.io requires."""
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(site.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(site).as_posix())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m loosethread.web.build", description=__doc__)
    parser.add_argument("--zip", action="store_true", help="also write a zip of the site")
    args = parser.parse_args(argv)
    site = build()
    print(f"site in {site}")
    if args.zip:
        target = site.parent / "loosethread-web.zip"
        zip_site(site, target)
        print(f"zip in {target}, {target.stat().st_size / 1048576:.1f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
