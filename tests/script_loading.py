"""Shared helpers for tests that exercise `scripts/` entries by path.

`scripts/` is deliberately not a package (its entries are standalone
operator/maintainer scripts, not importable library code), so tests that
need to reach into one for unit-level coverage load it by file path via
`importlib.util` instead of a normal import.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent


def import_script(name: str) -> ModuleType:
    """Import `scripts/<name>` by path, as a module named after its stem."""
    script = REPO_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(script.stem, script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
