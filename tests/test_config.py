"""Unit tests for cache-directory resolution and the raw-namespace cache singleton."""

from __future__ import annotations

from pathlib import Path

import pytest

from tossd_reader import config


def test_get_cache_dir_follows_env_var(tmp_path: Path) -> None:
    """With no explicit override, `get_cache_dir` resolves under the env var's tmp_path."""
    resolved = config.get_cache_dir()
    assert resolved is not None
    assert resolved.is_relative_to(tmp_path)


def test_set_cache_dir_explicit_path_wins_over_env_var(tmp_path: Path) -> None:
    """An explicit `set_cache_dir` override takes precedence over the env var."""
    override = tmp_path / "explicit-override"
    config.set_cache_dir(override)
    resolved = config.get_cache_dir()
    assert resolved is not None
    assert resolved.is_relative_to(override)


def test_set_cache_dir_none_is_ephemeral_bypass() -> None:
    """`set_cache_dir(None)` puts the cache in bypass mode: no resolved directory."""
    config.set_cache_dir(None)
    assert config.get_cache_dir() is None

    cache = config.get_cache()
    assert cache.entries() == []  # bypass mode persists nothing


def test_get_cache_rebuilds_when_effective_dir_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The cache singleton is rebuilt once the effective directory changes."""
    first = config.get_cache()
    monkeypatch.setenv("TOSSD_READER_CACHE_DIR", str(tmp_path / "other"))
    second = config.get_cache()
    assert first is not second


def test_get_cache_is_stable_when_effective_dir_is_unchanged() -> None:
    """Repeated calls with no directory change reuse the same singleton."""
    first = config.get_cache()
    second = config.get_cache()
    assert first is second


def test_set_cache_dir_closes_an_already_built_singleton(tmp_path: Path) -> None:
    """Calling `set_cache_dir` after `get_cache()` closes the old singleton, not just drops it."""
    config.get_cache()  # builds and caches the singleton
    config.set_cache_dir(tmp_path / "new-explicit-dir")
    assert config.get_cache_dir() is not None
    assert config.get_cache_dir().is_relative_to(tmp_path / "new-explicit-dir")
