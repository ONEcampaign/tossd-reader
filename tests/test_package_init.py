"""Tests for `tossd_reader`'s lazy public API (PEP 562) and its no-socket guarantee."""

from __future__ import annotations

import subprocess
import sys

import pytest

import tossd_reader
from tossd_reader import exceptions, query


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("get_tossd_raw", "tossd_reader.fetch"),
        ("get_vintages", "tossd_reader.fetch"),
        ("export", "tossd_reader._export"),
        ("verify_export", "tossd_reader._export"),
        ("load_export", "tossd_reader._export"),
        ("FORCED_COLUMNS", query.FORCED_COLUMNS),
        ("set_cache_dir", "tossd_reader.config"),
        ("set_offline", "tossd_reader.config"),
        ("get_offline", "tossd_reader.config"),
        ("cache_info", "tossd_reader.config"),
        ("clear_cache", "tossd_reader.config"),
        ("get_available_filters", "tossd_reader.codelists"),
        ("get_codelists_version", "tossd_reader.codelists"),
        ("explode_sdg", "tossd_reader.analysis"),
        ("add_iso3", "tossd_reader.analysis"),
        ("extract_keywords", "tossd_reader.analysis"),
        ("get_structural_breaks", "tossd_reader.analysis"),
        ("filter_provider_costs", "tossd_reader.analysis"),
        ("add_recipient_group", "tossd_reader.analysis"),
        ("add_instrument_group", "tossd_reader.analysis"),
        ("get_recipient_groups_version", "tossd_reader.analysis"),
        ("get_instrument_groups_version", "tossd_reader.analysis"),
        ("rank_entities", "tossd_reader.verbs"),
        ("compare_years", "tossd_reader.verbs"),
        ("sdg_totals", "tossd_reader.verbs"),
        ("keyword_totals", "tossd_reader.verbs"),
        ("subpillar_breakdown", "tossd_reader.verbs"),
        ("reconcile", "tossd_reader.verbs"),
        ("get_provenance", "tossd_reader.verbs"),
        ("TossdReaderError", exceptions.TossdReaderError),
        ("TossdNetworkError", exceptions.TossdNetworkError),
        ("VintageValidationError", exceptions.VintageValidationError),
        ("SchemaDriftError", exceptions.SchemaDriftError),
        ("UnknownCodeError", exceptions.UnknownCodeError),
        ("InvalidPillarError", exceptions.InvalidPillarError),
        ("ExportIntegrityError", exceptions.ExportIntegrityError),
    ],
)
def test_lazy_attribute_resolves(name: str, expected: object) -> None:
    """Every lazily-exported name resolves to the right underlying object."""
    resolved = getattr(tossd_reader, name)
    if isinstance(expected, str):
        assert resolved.__module__ == expected
    else:
        assert resolved is expected


def test_unknown_attribute_raises_attribute_error() -> None:
    """An unrecognised attribute still raises the normal `AttributeError`."""
    with pytest.raises(AttributeError, match="not_a_real_attribute"):
        _ = tossd_reader.not_a_real_attribute


def test_dir_reports_public_surface() -> None:
    """`dir(tossd_reader)` reports the full lazily-resolved public surface."""
    assert set(tossd_reader.__all__) <= set(dir(tossd_reader))


def test_import_opens_no_socket_and_stays_light() -> None:
    """`import tossd_reader` alone must not open a socket or import fetch/_discovery/config.

    Run in a fresh interpreter with socket connections monkeypatched to raise,
    mirroring `tests/conftest.py`'s own network-blocking fixture but for a
    bare import with no test harness involved.

    Each checked submodule is first confirmed to exist via `find_spec`, so a
    future rename fails loudly instead of the "not in sys.modules" assertion
    passing vacuously for a name that no longer refers to anything.
    """
    script = (
        "import socket\n"
        "def _blocked(*a, **k):\n"
        "    raise OSError('socket blocked')\n"
        "socket.socket.connect = _blocked\n"
        "socket.socket.connect_ex = _blocked\n"
        "import sys\n"
        "import importlib.util\n"
        "import tossd_reader\n"
        "lazy_submodules = [\n"
        "    'tossd_reader.fetch',\n"
        "    'tossd_reader._discovery',\n"
        "    'tossd_reader.config',\n"
        "    'tossd_reader.codelists',\n"
        "    'tossd_reader.query',\n"
        "    'tossd_reader._export',\n"
        "    'tossd_reader.analysis',\n"
        "    'tossd_reader.verbs',\n"
        "    'tossd_reader._accessor',\n"
        "]\n"
        "for name in lazy_submodules:\n"
        "    assert importlib.util.find_spec(name) is not None, f'{name} does not exist'\n"
        "for name in lazy_submodules:\n"
        "    assert name not in sys.modules\n"
        "assert 'resolvekit' not in sys.modules\n"
        "assert 'oda_reader' not in sys.modules\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"


def test_codelists_loader_never_imports_oda_reader() -> None:
    """Using the whole codelists loader surface still never imports `oda_reader`.

    `tossd_reader.codelists` reads only the packaged CSV snapshot; `oda_reader`
    is a maintainer-only dependency (the `codelists` group) that must never be
    reachable from a normal runtime import of this package.
    """
    script = (
        "import sys\n"
        "import tossd_reader\n"
        "tossd_reader.get_available_filters()\n"
        "tossd_reader.get_codelists_version()\n"
        "assert 'oda_reader' not in sys.modules\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"
