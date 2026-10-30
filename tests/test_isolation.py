"""Structural checks that the solver and difficulty metrics never touch the truth.

These read the source with `ast`, so they catch imports and attribute access by name. They cannot
catch truth smuggled in through data (e.g. a statement that happens to encode the culprit); the
generator's audit and the brute-force tests cover behaviour.
"""

import ast
from pathlib import Path

import pytest

import loosethread

PACKAGE = Path(loosethread.__file__).parent
TRUTH_NAMES = {"Truth", "Lie", "Knowledge", "Event", "EventKind", "LieReason", "Case"}
FORBIDDEN_MODULES = {
    "loosethread.generator",
    "loosethread.lookup",
    "loosethread.audit",
    "loosethread.content",
    "loosethread.case",
}


@pytest.mark.parametrize("module", ["solver.py", "difficulty.py"])
def test_module_cannot_reach_truth(module: str) -> None:
    tree = ast.parse((PACKAGE / module).read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
    assert not imported_modules & FORBIDDEN_MODULES
    assert not imported_names & TRUTH_NAMES
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    identifiers = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "truth" not in attributes | identifiers
