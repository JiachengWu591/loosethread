"""Package-level invariants: version metadata and the stdlib-only core rule."""

import ast
import sys
from pathlib import Path

import loosethread

PACKAGE_ROOT = Path(loosethread.__file__).parent
# Subpackages that may use optional third-party dependencies (installed via extras).
OPTIONAL_SUBPACKAGES = frozenset({"llm", "web"})


def _core_modules() -> list[Path]:
    return [
        path
        for path in PACKAGE_ROOT.rglob("*.py")
        if path.relative_to(PACKAGE_ROOT).parts[0] not in OPTIONAL_SUBPACKAGES
    ]


def _imported_top_level_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_version_is_a_string() -> None:
    assert isinstance(loosethread.__version__, str)


def test_core_modules_exist() -> None:
    assert _core_modules(), "expected at least one core module"


def test_core_imports_only_stdlib() -> None:
    allowed = set(sys.stdlib_module_names) | {"loosethread"}
    offenders = {
        str(path.relative_to(PACKAGE_ROOT)): sorted(_imported_top_level_names(path) - allowed)
        for path in _core_modules()
    }
    assert {module: names for module, names in offenders.items() if names} == {}
