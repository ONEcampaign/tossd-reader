# How to work offline and manage the cache

Prime the local cache while connected, then switch `tossd-reader` into offline mode so `get_tossd` and `get_vintages` serve from disk without requiring network access.

## Prime the cache while connected

Fetch every required year before disconnecting. Each requested year downloads once and caches locally.

```python
import tossd_reader as tossd

tossd.get_tossd(years=range(2019, 2025))
```

All six published years together cache to about 0.45 GB on disk.

## Enable offline mode

Enable offline mode for the running session or across the shell environment.

```python
import tossd_reader as tossd

tossd.set_offline(True)
```

```bash
export TOSSD_READER_OFFLINE=1
```

Recognised truthy values for the environment variable are `1`, `true`, and `yes`, case-insensitive; `0`, `false`, `no`, and unset all leave offline mode off. `set_offline(True)` and `set_offline(False)` override the environment variable for the running process. `set_offline(None)` removes the override and resumes reading the environment variable.

## Offline query behaviour

With a year already cached, `get_tossd` returns the local vintage and emits a warning that it is serving from disk.

```python
tossd.set_offline(True)
df = tossd.get_tossd(years=2024)
```

```text
UserWarning: Offline mode is active (tossd_reader.config.set_offline(False), or the TOSSD_READER_OFFLINE env var, would allow network access); serving the cached 2024 vintage retrieved 2026-08-28T19:32:28.617740+00:00 (etag "69e6ac8d-5728379").
```

Requesting an unprimed year raises `TossdNetworkError`.

```python
tossd.get_tossd(years=2010)
```

```text
TossdNetworkError: Cannot fetch 2010: offline mode is active (tossd_reader.config.set_offline(False), or the TOSSD_READER_OFFLINE env var, would allow network access), and no cached vintage for 2010 exists in <your cache directory>.
```

The full error message names the resolved cache directory. See [Cache location and bounds](../reference/configuration.md#cache-location-and-bounds) for default platform paths.

## Refresh behaviour in offline mode

Passing `refresh=True` requires network connectivity to check for updated vintages. Combining `refresh=True` with offline mode raises `ValueError` immediately.

```python
tossd.get_tossd(years=2024, refresh=True)
```

```text
ValueError: get_tossd(refresh=True) conflicts with offline mode (config.get_offline() is True): a forced refresh needs the network. Call tossd_reader.config.set_offline(False) first, or omit refresh=True.
```

The same conflict occurs with `get_tossd_raw`, `export`, and `get_vintages` whenever `refresh=True` and offline mode is active.

## Inspect cached and live vintages

`cache_info()` lists every locally cached vintage, with one row per download. A re-downloaded or republished year generates multiple rows.

```python
tossd.cache_info().drop(columns=["path"])
```

```text
   year                etag                      retrieved_at                    downloaded_at  size_bytes
0  2019  "69e6ac86-347a653"  2026-08-28T21:14:14.414671+00:00 2026-09-02 08:05:04.508371+00:00    55027283
1  2021  "69e6ac8b-4112f49"  2026-08-28T21:14:42.382179+00:00 2026-08-28 21:14:42.356395+00:00    68235081
2  2020  "69e6ac8a-3c90446"  2026-08-28T21:14:28.358434+00:00 2026-08-28 21:14:28.331745+00:00    63505478
3  2022  "69e6ac8b-4e95ca1"  2026-08-28T21:14:57.492221+00:00 2026-08-28 21:14:57.461650+00:00    82402465
4  2024  "69e6ac8d-5728379"  2026-08-28T19:32:28.617740+00:00 2026-08-28 19:32:28.582136+00:00    91390841
5  2023  "69e6ac8c-56469db"  2026-08-28T21:15:12.643113+00:00 2026-08-28 21:15:12.608318+00:00    90466779
```

`get_vintages()` reports live vintages published on the remote host, with one row per year.

```python
tossd.get_vintages()
```

```text
   year                                          url                     etag                  last_modified  size_bytes
0  2019  https://tossd.online/tossddata_2019.parquet  "347a653-64fec0e08ffa0"  Mon, 20 Apr 2026 22:45:26 GMT    55027283
1  2020  https://tossd.online/tossddata_2020.parquet  "3c90446-64fec0e456c55"  Mon, 20 Apr 2026 22:45:30 GMT    63505478
2  2021  https://tossd.online/tossddata_2021.parquet  "4112f49-64fec0e4f7e73"  Mon, 20 Apr 2026 22:45:31 GMT    68235081
3  2022  https://tossd.online/tossddata_2022.parquet  "4e95ca1-64fec0e5ae851"  Mon, 20 Apr 2026 22:45:31 GMT    82402465
4  2023  https://tossd.online/tossddata_2023.parquet  "56469db-64fec0e66fe0f"  Mon, 20 Apr 2026 22:45:32 GMT    90466779
5  2024  https://tossd.online/tossddata_2024.parquet  "5728379-64fec0e73236d"  Mon, 20 Apr 2026 22:45:33 GMT    91390841
```

<!-- prettier-ignore -->
!!! warning "Comparing ETag values between cache and server"
    The publisher's host serves different ETag formats for identical payloads across requests. Compare 2019 above (`"347a653-64fec0e08ffa0"`) against the same year in `cache_info()` (`"69e6ac86-347a653"`). Avoid direct equality checks between the two. A revised file receives a new ETag, but a mismatch between `get_vintages()` and `cache_info()` indicates a need to re-verify rather than confirming new data.

In offline mode or when the publisher is unreachable, `get_vintages()` falls back to listing locally cached vintages.

```python
tossd.get_vintages()
```

```text
UserWarning: Offline mode is active (config.get_offline() is True); listing vintages from the local cache instead of a live discovery sweep (last_modified is unavailable this way).
   year                                          url                etag last_modified  size_bytes
0  2019  https://tossd.online/tossddata_2019.parquet  "69e6ac86-347a653"          None    55027283
...
```

The `last_modified` field contains `None` in fallback mode because that metadata is populated directly from the publisher's HTTP response headers.

## Free up cache space

`clear_cache()` returns the number of entries removed. A default call without arguments removes superseded vintages that a newer download has replaced.

```python
tossd.clear_cache()
```

```text
0
```

On a cache holding one vintage per year, nothing is superseded, so a default `clear_cache()` call removes 0 entries. The `keep_latest=True` setting protects each year's newest vintage, including when filtering with `years=` or `before=`.

```python
tossd.clear_cache(keep_latest=False)
```

```text
6
```

```python
len(tossd.cache_info())
```

```text
0
```

Setting `keep_latest=False` without other filters empties the entire cache. Provide `years=` or `before=` to remove targeted subsets.

```python
tossd.clear_cache(years=2019)
tossd.clear_cache(before="2026-01-01")
```

`years=` accepts a single year or an iterable of years. `before=` accepts a `date`, a `datetime`, or an ISO 8601 string, treating naive timestamps without timezone information as UTC. Both arguments default to `keep_latest=True`; set `keep_latest=False` to remove the latest matching vintage as well.

## Verify it worked

Confirm that every primed year exists in the cache.

```python
sorted(tossd.cache_info()["year"])
```

```text
[2019, 2020, 2021, 2022, 2023, 2024]
```

Querying a cached year while disconnected emits a `UserWarning` naming the local vintage, confirming that offline serving is active.

## Troubleshooting

**A query raises `TossdNetworkError` for a year expected to work offline.** That year was not primed. Reconnect, prime it with `get_tossd`, and query again. See [Prime the cache while connected](#prime-the-cache-while-connected).

**`TOSSD_READER_OFFLINE` is set but offline mode is not active.** The value is not one of the recognised truthy forms.

```bash
TOSSD_READER_OFFLINE=on python analysis.py
```

```text
UserWarning: TOSSD_READER_OFFLINE='on' is not a recognized value; offline mode is NOT active. Recognised truthy values are 1, true, yes (case-insensitive).
```

Use `1`, `true`, or `yes` instead.

## See also

- [Configuration reference](../reference/configuration.md) for cache location defaults, the full warnings and errors table, and cache directory configuration.
- [About reproducibility and the cache](../about/reproducibility.md) for tracking data vintages and ETags.
