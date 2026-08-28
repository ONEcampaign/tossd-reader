"""Shared pytest fixtures for tossd_reader tests."""

import socket
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _tossd_reader_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point ``TOSSD_READER_CACHE_DIR`` at a per-test ``tmp_path``.

    Ensures no test ever reads from or writes to a real user cache directory.
    """
    monkeypatch.setenv("TOSSD_READER_CACHE_DIR", str(tmp_path))


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
