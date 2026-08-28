"""End-to-end tests for `scripts/archive_vintage.sh`.

Drives the real script via `subprocess`, pointed (via `TOSSD_ARCHIVE_URL_PREFIX`)
at a local `http.server` running in a background thread on an ephemeral
loopback port. No real network access anywhere in this file — the script's
own `curl` calls are the only thing hitting a socket, and they only ever
reach `127.0.0.1`.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "archive_vintage.sh"

_YEAR_RE = re.compile(r"tossddata_(\d+)\.parquet$")


def _year_from_path(path: str) -> int:
    """Extract the requested year from a `tossddata_<year>.parquet` request path."""
    match = _YEAR_RE.search(path)
    assert match, f"unexpected request path: {path}"
    return int(match.group(1))


def _make_handler(
    payloads: dict[int, bytes], *, truncate_year: int | None = None
) -> type[BaseHTTPRequestHandler]:
    """Build a request handler serving `payloads` by year, 404 otherwise.

    If `truncate_year` is set, that year is answered with a `Content-Length`
    larger than the bytes actually written, then the connection is closed —
    simulating an interrupted transfer rather than a genuine 404.
    """

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass  # keep test output quiet

        def do_GET(self) -> None:
            year = _year_from_path(self.path)

            if truncate_year is not None and year == truncate_year:
                body = b"short"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body) + 1000))
                self.end_headers()
                self.wfile.write(body)
                self.close_connection = True
                return

            if year in payloads:
                body = payloads[year]
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_response(404)
            self.end_headers()

    return _Handler


_ServerFactory = Callable[[type[BaseHTTPRequestHandler]], str]


@pytest.fixture
def _server_factory() -> Iterator[_ServerFactory]:
    """Yield a factory that starts a threaded HTTP server for a given handler.

    Servers created via the factory are torn down automatically at test end.
    """
    servers: list[ThreadingHTTPServer] = []

    def _start(handler_class: type[BaseHTTPRequestHandler]) -> str:
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        servers.append(server)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        return f"http://127.0.0.1:{port}/tossddata_"

    yield _start

    for server in servers:
        server.shutdown()
        server.server_close()


def _run_archive(
    url_prefix: str, archive_dir: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), str(archive_dir)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "TOSSD_ARCHIVE_URL_PREFIX": url_prefix},
    )


def test_archives_published_years_with_verifiable_manifest(
    _server_factory: _ServerFactory, tmp_path: Path
) -> None:
    """Two published years land as payload+headers, and the manifest verifies."""
    payloads = {
        2019: b"YEAR-2019-FAKE-PARQUET-DATA",
        2020: b"YEAR-2020-FAKE-PARQUET-DATA",
    }
    url_prefix = _server_factory(_make_handler(payloads))
    archive_dir = tmp_path / "archive"

    result = _run_archive(url_prefix, archive_dir)

    assert result.returncode == 0, result.stderr
    for year, body in payloads.items():
        payload_file = archive_dir / f"tossddata_{year}.parquet"
        headers_file = archive_dir / f"tossddata_{year}.headers.txt"
        assert payload_file.read_bytes() == body
        assert headers_file.exists()
        assert headers_file.stat().st_size > 0

    assert (archive_dir / "README.md").exists()

    verify = subprocess.run(
        ["shasum", "-a", "256", "-c", "sha256sums.txt"],
        cwd=archive_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert verify.returncode == 0, verify.stdout + verify.stderr


def test_skips_unpublished_year_cleanly(
    _server_factory: _ServerFactory, tmp_path: Path
) -> None:
    """A genuine 404 for every year is skipped cleanly: exit 0, no stray files."""
    url_prefix = _server_factory(_make_handler({}))
    archive_dir = tmp_path / "archive"

    result = _run_archive(url_prefix, archive_dir)

    assert result.returncode == 0, result.stderr
    assert not list(archive_dir.glob("*.parquet"))
    assert not list(archive_dir.glob("*.headers.txt"))
    assert (archive_dir / "sha256sums.txt").read_text() == ""


def test_interrupted_transfer_is_reported_as_transfer_error_not_404(
    _server_factory: _ServerFactory, tmp_path: Path
) -> None:
    """A truncated transfer fails the run and is reported distinctly from a 404."""
    truncated_year = 2019
    url_prefix = _server_factory(_make_handler({}, truncate_year=truncated_year))
    archive_dir = tmp_path / "archive"

    result = _run_archive(url_prefix, archive_dir)

    assert result.returncode != 0
    combined_output = result.stdout + result.stderr
    assert "not treating this as an unpublished year" in combined_output
    assert f"HTTP 404; {truncated_year}" not in combined_output

    manifest = (archive_dir / "sha256sums.txt").read_text()
    assert str(truncated_year) not in manifest
    assert not (archive_dir / f"tossddata_{truncated_year}.parquet").exists()
    assert not (archive_dir / f"tossddata_{truncated_year}.headers.txt").exists()
