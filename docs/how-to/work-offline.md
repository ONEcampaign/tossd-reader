# How to work offline and manage the cache

Download and prime TOSSD data files while online so that `get_tossd` and `get_tossd_raw` operate locally without network access.

## Prime the cache before you go offline

1. **Call `get_tossd` while connected to the network.** Specify every year required for offline analysis.

   ```python
   import tossd_reader as tossd

   tossd.get_tossd(years=range(2019, 2025))
   ```

   Each requested year downloads and caches as a local parquet file. All six published years (2019 to 2024) use approximately 0.45 GB of disk space.

2. **Query cached data in offline environments.** When running offline, `get_tossd` serves the locally cached parquet files and emits a `UserWarning` indicating the cached vintage date and ETag. If a requested year is missing from the local cache, the call raises `TossdNetworkError` with the checked cache path.

   ```python
   import tossd_reader as tossd
   from tossd_reader import TossdNetworkError

   try:
       df = tossd.get_tossd(years=2024)
   except TossdNetworkError as exc:
       print(exc)
   ```

## Verify it worked

Request the primed years with the network disconnected. All years return directly from the local cache.

```python
primed = tossd.get_tossd(years=range(2019, 2025), columns="minimal")
primed["year"].nunique()
```

```text
6
```

A `UserWarning` per year confirms the cached vintage served from local storage.

## Configure the cache directory

Set `TOSSD_READER_CACHE_DIR` in the environment or call `set_cache_dir` from Python. The function call takes precedence over the environment variable for the running process.

```python
import tossd_reader as tossd

tossd.set_cache_dir("/data/tossd-cache")
```

## Use ephemeral storage (stateless mode)

Passing `None` to `set_cache_dir` enables ephemeral mode. Downloaded files reside in a temporary directory that is removed when the process exits or when `set_cache_dir` is called again.

```python
tossd.set_cache_dir(None)
```

Ephemeral mode suits CI pipelines and automated testing where persistent local cache is unwanted.

## Force a fresh download

Pass `refresh=True` to download the latest file for a single call, or use `readerkit.refresh_scope` across a block of queries.

```python
import readerkit
import tossd_reader as tossd

with readerkit.refresh_scope():
    tossd.get_tossd(years=2023)
    tossd.get_tossd(years=2024)
```

## Troubleshooting

- **A cache warning appears without a network error.** A cached vintage was served because tossd.online was unreachable. Reconnect and run with `refresh=True` to check for newer vintages.
- **`TossdNetworkError` while connected.** Verify `TOSSD_READER_CACHE_DIR`, `BBLOCKS_CACHE_DIR`, and any `set_cache_dir` call in the current process to ensure the path points to an accessible directory.

## See also

- [Configuration reference](../reference/configuration.md) for environment variables, default paths per platform, and network retry behaviour.
- [Reproducibility and vintages](../about/reproducibility.md) for how ETags track data updates.
