# How to work offline and manage the cache

Prime the cache while you're online, and `get_tossd`/`get_tossd_raw` keep serving data once you're not.

## Prime the cache before you go offline

1. While you still have network access, call `get_tossd` (or `get_tossd_raw`) naming every year you'll need. A single call can cover all of them:

   ```python
   import tossd_reader as tossd

   tossd.get_tossd(years=range(2019, 2025))
   ```

   Each requested year downloads and caches on its own, so this is the same as one full call per year, batched into one statement. All six published years (2019 to 2024) take about 0.45 GB (450 MB) on disk.

2. Verify before you disconnect. Turn off the network and make the same call again. A `UserWarning` naming a cached vintage means that year is there. `TossdNetworkError` means it isn't (see the next section).

## What happens when you go offline

`get_tossd` and `get_tossd_raw` don't fail outright just because the publisher is unreachable:

- **A cached vintage exists for the requested year.** It's served, and tossd_reader emits a `UserWarning` naming the reason, the year, when that cached vintage was retrieved, and its ETag if it has one. Python's default warning filter shows each distinct message once per process, and the message names the year and vintage, so expect one line per stale year served.
- **Nothing is cached for that year.** The call raises `TossdNetworkError`, naming the cache directory it checked.

```python
from tossd_reader import TossdNetworkError

try:
    df = tossd.get_tossd(years=2024)
except TossdNetworkError as exc:
    print(exc)
```

## Point the cache at a different directory

Two ways, both read by every subsequent call:

- Set `TOSSD_READER_CACHE_DIR` in the environment. tossd_reader re-reads it on every call, so changing it between calls, or between processes, takes effect with no reset step.
- Call `set_cache_dir(path)` from Python. It takes precedence over the environment variable for the rest of the process.

```python
tossd.set_cache_dir("/data/tossd-cache")
```

## Skip the cache entirely (ephemeral mode)

`set_cache_dir(None)` switches to ephemeral mode. Fetches go to a temporary directory that's torn down at the end of the process, or at the next `set_cache_dir` call, and nothing written during that time persists.

```python
tossd.set_cache_dir(None)
```

Use this in a short script or a CI job where a cache directory left on disk isn't wanted. Repeat calls within the same process still hit the temporary directory. Only a new process starts with an empty cache.

## Force a fresh download

Two ways to bypass the cached vintage and pull from the publisher again:

- Pass `refresh=True` to one call: `tossd.get_tossd(years=2024, refresh=True)`.
- Wrap several calls in `readerkit.refresh_scope()` to force all of them, once per key, for the whole block:

  ```python
  import readerkit
  import tossd_reader as tossd

  with readerkit.refresh_scope():
      tossd.get_tossd(years=2023)
      tossd.get_tossd(years=2024)
  ```

## Where the cache lives

Default location:

- macOS: `~/Library/Caches/readerkit/v1/tossd-reader/1`
- Linux: `~/.cache/readerkit/v1/tossd-reader/1`

Downloaded payloads live under `artifacts/raw/` inside that directory, as content-keyed files. Each one is paired with a `.provenance.json` sidecar recording the source URL, ETag, size, checksum, row count, retrieval timestamp, and the tossd_reader version that fetched it. Six vintages (2019 to 2024) take about 0.45 GB total. Per-year files run 55 to 91 MB. The cache keeps whichever bound hits first of the newest 24 entries or 4 GB, both fixed.

!!! info "Why"

    The cache key embeds the vintage's ETag, so a fixed key always points at the same bytes. Staleness is decided at the discovery layer, by whether the publisher has issued a new ETag, not by a time-to-live clock.

!!! warning "Heads up"

    The offline warning above is the only signal that a result was built
    from a stale vintage. Don't silence `UserWarning`s in unattended
    offline runs.

## Troubleshooting

- **A warning appears but nothing errors.** A cached vintage was served because the network, or the publisher, was unreachable for that year. Reconnect and call again with `refresh=True` (or inside `refresh_scope()`) to check for a newer vintage.
- **`TossdNetworkError` even though you're online.** Check `TOSSD_READER_CACHE_DIR` and any `set_cache_dir` call in your process. You may be pointed at an empty or unexpected directory.

## See also

- [About caching](../about/caching.md) for the ETag-based cache-key design.
- [Configuration reference](../reference/configuration.md) for the full `set_cache_dir` and `TOSSD_READER_CACHE_DIR` surface.
