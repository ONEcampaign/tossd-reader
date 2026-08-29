"""Shared pytest fixtures for tossd_reader tests."""

import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

from tossd_reader import _discovery, _pillars, config, query


@pytest.fixture(autouse=True, scope="session")
def _session_cache_dir_floor(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    """Session-wide floor under the per-test cache-dir override.

    The function-scoped ``_tossd_reader_cache_dir`` fixture only covers each
    test's own body. Higher-scoped fixtures (instantiated before
    function-scoped ones) and anything running between tests would otherwise
    see an unset ``TOSSD_READER_CACHE_DIR`` and fall through to the user's
    real platformdirs cache directory. Import-time code is beyond any
    fixture's reach — collection finishes before fixtures run — but
    ``test_package_init.py`` separately enforces that importing the package
    touches no cache.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(
            "TOSSD_READER_CACHE_DIR",
            str(tmp_path_factory.mktemp("session-cache-floor")),
        )
        yield


@pytest.fixture(autouse=True)
def _tossd_reader_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point ``TOSSD_READER_CACHE_DIR`` at a per-test ``tmp_path``.

    Ensures no test ever reads from or writes to a real user cache directory.
    """
    monkeypatch.setenv("TOSSD_READER_CACHE_DIR", str(tmp_path))


@pytest.fixture(autouse=True)
def _reset_discovery_config_query_and_pillars_state() -> None:
    """Reset _discovery's, config's, query's, and _pillars's module state before each test.

    All four modules memoise state at module scope (_discovery's HEAD-sweep
    memo and warn-once set; config's cache-dir override and cache singleton;
    query's warn-once set for unknown-decode-code warnings; _pillars's
    warn-once flags for the sub-pillar-narrowing and 2023-coverage
    warnings), so a test that doesn't reset them can leak fake data or a
    stale singleton across test files. Fetch's and _schema's own warn-once
    state is reset locally instead, each via its own per-file fixture.
    """
    _discovery._reset_for_tests()
    config._reset_for_tests()
    query._reset_for_tests()
    _pillars._reset_for_tests()


class NetworkBlockedError(OSError):
    """Raised when a test attempts a socket connection without the network marker."""


@pytest.fixture(autouse=True)
def _block_network(request: pytest.FixtureRequest) -> Iterator[None]:
    """Disable outbound socket connections for tests not marked ``network``.

    Tests marked with ``@pytest.mark.network`` are exempt from blocking (and
    are already deselected by default via the ``-m "not network"`` addopts).

    Raises ``NetworkBlockedError`` (an ``OSError`` subclass) rather than a
    plain ``RuntimeError`` so that library code with ``except OSError``
    cleanup paths (e.g. the stdlib's ``socket.create_connection``) still
    closes the socket normally instead of leaking an unraisable-exception
    warning at garbage-collection time.
    """
    if request.node.get_closest_marker("network") is not None:
        yield
        return

    def _blocked_connect(*_args: object, **_kwargs: object) -> None:
        raise NetworkBlockedError(
            "Network access is blocked in tests; mark with "
            "@pytest.mark.network if this test genuinely needs the network."
        )

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    socket.socket.connect = _blocked_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _blocked_connect  # type: ignore[method-assign]
    try:
        yield
    finally:
        socket.socket.connect = original_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = original_connect_ex  # type: ignore[method-assign]
