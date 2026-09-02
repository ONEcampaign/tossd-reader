# How to work offline and manage the cache

Prime the local cache while connected, then switch `tossd-reader` into offline mode so `get_tossd` and `get_vintages` serve from disk with no network access at all.

## Prime the cache while you're online

Fetch every year you'll need before you disconnect. Each requested year downloads once and caches locally.

```python
import tossd_reader as tossd

tossd.get_tossd(years=range(2019, 2025))
```

All six published years together cache to about 0.45 GB on disk.

## Turn on offline mode

Turn it on for the running session, or for the whole environment.

```python
import tossd_reader as tossd

tossd.set_offline(True)
```

```bash
export TOSSD_READER_OFFLINE=1
```

Recognized truthy values for the environment variable are `1`, `true`, and `yes`, case-insensitive; `0`, `false`, `no`, and unset all leave offline mode off. `set_offline(True)`/`set_offline(False)` overrides the environment variable for the running process. `set_offline(None)` drops the override and goes back to reading the environment variable.

## What offline serving looks like

With a year already cached, `get_tossd` returns it and warns that it's serving from disk instead of the network.

```python
tossd.set_offline(True)
df = tossd.get_tossd(years=2024)
```

```text
UserWarning: Offline mode is active (tossd_reader.config.set_offline(False), or the TOSSD_READER_OFFLINE env var, would allow network access); serving the cached 2024 vintage retrieved 2026-08-28T19:32:28.617740+00:00 (etag "69e6ac8d-5728379").
```

Request a year that was never primed and there's nothing to serve. `get_tossd` raises `TossdNetworkError` instead of warning.

```python
tossd.get_tossd(years=2010)
```

```text
TossdNetworkError: Cannot fetch 2010: offline mode is active (tossd_reader.config.set_offline(False), or the TOSSD_READER_OFFLINE env var, would allow network access), and no cached vintage for 2010 exists in <your cache directory>.
```

The real message names your resolved cache directory. See [Cache location and bounds](../reference/configuration.md#cache-location-and-bounds) for the default per platform.

## Forcing a refresh while offline

`refresh=True` needs the network to check for a newer vintage, which is exactly what offline mode rules out. Passing both raises immediately, before any fetch is attempted.

```python
tossd.get_tossd(years=2024, refresh=True)
```

```text
ValueError: get_tossd(refresh=True) conflicts with offline mode (config.get_offline() is True): a forced refresh needs the network. Call tossd_reader.config.set_offline(False) first, or omit refresh=True.
```

The same conflict fires from `get_tossd_raw`, `export`, and `get_vintages` whenever `refresh=True` and offline mode is active.

## Inspect what's cached and what's live

`cache_info()` lists every locally cached vintage, one row per download. A re-downloaded, republished year gets more than one row.

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

`get_vintages()` reports what the publisher has live right now, one row per year.

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
!!! warning "Heads up"
    The publisher's host doesn't always serve the same ETag format for identical bytes. Compare 2019 above (`"347a653-64fec0e08ffa0"`) against the same year in `cache_info()` (`"69e6ac86-347a653"`). Don't equality-check the two. A revised file does get a new ETag, but a mismatch between `get_vintages()` and `cache_info()` means "re-verify," not "new data."

Offline, or when the publisher is unreachable, `get_vintages()` falls back to listing whatever's cached locally instead of raising.

```python
tossd.get_vintages()
```

```text
UserWarning: Offline mode is active (config.get_offline() is True); listing vintages from the local cache instead of a live discovery sweep (last_modified is unavailable this way).
   year                                          url                etag last_modified  size_bytes
0  2019  https://tossd.online/tossddata_2019.parquet  "69e6ac86-347a653"          None    55027283
...
```

`last_modified` reads `None` in the fallback. That header only comes from the publisher's own HEAD response, and it's never persisted locally.

## Free up cache space

`clear_cache()` returns the number of entries it removed. The bare call, with every argument at its default, drops only superseded vintages, the ones a republish has since replaced.

```python
tossd.clear_cache()
```

```text
0
```

On a cache holding one vintage per year, nothing is superseded, so a bare call removing 0 entries is the point of its default, not a bug. `keep_latest=True` protects each year's newest vintage even from `years=`/`before=` filters below.

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

`keep_latest=False` drops the newest vintage too, so with no other filters it empties the whole cache. Narrow to specific years, or to vintages retrieved before a given point, without touching the rest.

```python
tossd.clear_cache(years=2019)
tossd.clear_cache(before="2026-01-01")
```

`years=` takes a single year or an iterable of years. `before=` takes a `date`, a `datetime`, or an ISO 8601 string; a naive value (no timezone) is treated as UTC. Both still default to `keep_latest=True`, so add `keep_latest=False` to also remove the newest match.

## Verify it worked

Confirm every year you primed is in the cache.

```python
sorted(tossd.cache_info()["year"])
```

```text
[2019, 2020, 2021, 2022, 2023, 2024]
```

Then query one of them with the network disconnected, as in [What offline serving looks like](#what-offline-serving-looks-like) above. A `UserWarning` naming the cached vintage, not a `TossdNetworkError`, confirms offline mode is serving from disk.

## Troubleshooting

**A query raises `TossdNetworkError` for a year you expected to work offline.** That year was never cached. Reconnect, prime it with `get_tossd`, and try again. See [Prime the cache while you're online](#prime-the-cache-while-youre-online).

**`TOSSD_READER_OFFLINE` is set but offline mode doesn't seem active.** The value isn't one of the recognized truthy forms.

```bash
TOSSD_READER_OFFLINE=on python analysis.py
```

```text
UserWarning: TOSSD_READER_OFFLINE='on' is not a recognized value; offline mode is NOT active. Recognised truthy values are 1, true, yes (case-insensitive).
```

Use `1`, `true`, or `yes` instead.

## See also

- [Configuration reference](../reference/configuration.md) for cache location defaults, the full warnings and errors table, and the `set_cache_dir`/`get_cache_dir` functions.
- [About reproducibility and the cache](../about/reproducibility.md) for why vintages and ETags matter for reproducible analysis.
