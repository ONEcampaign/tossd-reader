# Contributing

Dev setup, tests, and lint for tossd-reader.

## Set up

```bash
uv sync
```

Installs the package and the `dev` dependency group: pytest, ruff, ty, pre-commit.

## Run the tests

```bash
uv run pytest
```

Run it from the repo root. The suite deselects network-marked tests by default (`-m "not network"` in `pyproject.toml`), so it needs no network access.

For a single file, run this instead.

```bash
uv run pytest tests/test_codes.py -q --no-cov
```

## Lint and format

```bash
uv run ruff check
uv run ruff format
```

pre-commit adds type checking (`ty`), spelling (`codespell`), Markdown formatting, and general file hygiene on top. Scope it to the files you touched.

```bash
pre-commit run --files src/tossd_reader/config.py tests/test_config.py
```

Avoid `pre-commit run --all-files`. Several hooks already skip `src/tossd_reader/_data/`, the packaged OECD codelist snapshot, because reformatting it would corrupt a published schema hash and the ISO3 values it carries. A full run still walks every other file in the repo and can pull in unrelated changes.

## Cache isolation

pytest isolates itself from your real download cache automatically. A session-scoped fixture floors `TOSSD_READER_CACHE_DIR` at a temporary directory before any test runs, and a guard fixture fails the run if the real cache directory gets touched anyway.

A script or REPL session outside pytest reads the same variable (or the platform default) as any real user. Point it at a scratch directory first.

```bash
export TOSSD_READER_CACHE_DIR=/tmp/tossd-reader-scratch
```

Skip this and experimental fixture data lands in your real cache, where `clear_cache(keep_latest=True)` can end up protecting that fake entry over a genuine vintage.
