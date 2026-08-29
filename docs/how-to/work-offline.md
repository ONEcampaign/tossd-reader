# How to work offline and manage the cache

Prime the cache while you are online. `get_tossd` and `get_tossd_raw` then serve those years with no network.

## Prime the cache before you go offline

1. **Call `get_tossd` with network access.** Name every year you'll need. One call can cover all of them:

   ```python
   import tossd_reader as tossd

   tossd.get_tossd(years=range(2019, 2025))
   ```

Each requested year downloads and caches on its own. All six published years (2019 to 2024) take about 0.45 GB on disk.

2. **Make the same call offline.** A `UserWarning` naming a cached vintage confirms that year is available.

## What happens when you go offline

- **A cached vintage exists for the requested year.** It's served, with a `UserWarning` naming the year, when that vintage was retrieved, and its ETag if it has one.
- **Nothing is cached for that year.** The call raises `TossdNetworkError`, naming the cache directory it checked.

```python
import tossd_reader as tossd
from tossd_reader import TossdNetworkError

try:
    df = tossd.get_tossd(years=2024)
except TossdNetworkError as exc:
    print(exc)
```

## Verify it worked

With the network off, request every year you primed. All six come back from the cache:

```python
primed = tossd.get_tossd(years=range(2019, 2025), columns="minimal")
primed["year"].nunique()
```

```text
6
```

A `UserWarning` per year names the cached vintage it served.

## Point the cache at a different directory

- Set `TOSSD_READER_CACHE_DIR` in the environment. tossd_reader re-reads it on every call.
- Call `set_cache_dir(path)` from Python. It takes precedence over the environment variable for the rest of the process.

```python
import tossd_reader as tossd

tossd.set_cache_dir("/data/tossd-cache")
```

## Skip the cache entirely (ephemeral mode)

`set_cache_dir(None)` switches to ephemeral mode. Fetches go to a temporary directory that's torn down at the end of the process, or at the next `set_cache_dir` call, and nothing written during that time persists.

```python
tossd.set_cache_dir(None)
```

Use this in a short script or a CI job that should leave nothing on disk.

## Force a fresh download

- Pass `refresh=True` to one call: `tossd.get_tossd(years=2024, refresh=True)`.
- Wrap several calls in `readerkit.refresh_scope()` to force all of them, once per key, for the whole block:

  ```python
  import readerkit
  import tossd_reader as tossd

  with readerkit.refresh_scope():
      tossd.get_tossd(years=2023)
      tossd.get_tossd(years=2024)
  ```

## Troubleshooting

- **A warning appears but nothing errors.** A cached vintage was served because the publisher was unreachable for that year. Reconnect and call again with `refresh=True` to check for a newer vintage.
- **`TossdNetworkError` even though you're online.** Check `TOSSD_READER_CACHE_DIR`, `BBLOCKS_CACHE_DIR`, and any `set_cache_dir` call in your process. You may be pointed at an empty or unexpected directory.

## See also

- [Configuration reference](../reference/configuration.md) for the `set_cache_dir`/`TOSSD_READER_CACHE_DIR` surface, the default cache directory per platform, and the ETag-based retry protocol.
