# How to read the published columns unchanged

Call `get_tossd_raw` to get a year's TOSSD file exactly as the publisher
wrote it: publisher column names, publisher dtypes, publisher column order,
every row.

<!-- prettier-ignore -->
!!! info "Why"
    Three real reasons to reach for this over `get_tossd`.

    - Checking what the publisher actually shipped before trusting the
      normalisation.
    - Isolating the exact value behind a `SchemaDriftError`. The error
      fires during normalisation, and the raw read sidesteps that step
      entirely.
    - Reconciling a total against the TOSSD Secretariat's own portal, which
      reports the publisher's own column names and values.

## Steps

1. **Query the year with `get_tossd_raw`.** It takes `years` and `refresh`
   only, no filters:

   ```python
   import tossd_reader as tossd

   raw = tossd.get_tossd_raw(years=2024)
   raw.shape
   ```

   ```text
   (474026, 53)
   ```

   474,026 rows, one per activity, same as `get_tossd` returns for 2024 with
   no filters applied. 53 columns, the publisher's own count.

2. **Look at the column names.** They're the publisher's own headers,
   unrenamed:

   ```python
   list(raw.columns[:10])
   ```

   ```text
   ['Year', 'provider', 'ProviderNameE', 'agencyname_E', 'tossdid', 'ProjectNumber', 'recipientcode', 'recipientnamee', 'regionnamee', 'Channel']
   ```

   `get_tossd`'s renamed equivalents for the first three: `year`,
   `provider_code`, `provider_name`.

3. **Check the dtypes.** Every column is `str` or `float64`, the two dtypes
   parquet plus pandas produce with no casting applied:

   ```python
   raw.dtypes.value_counts()
   ```

   ```text
   str        44
   float64     9
   Name: count, dtype: int64
   ```

   A code column that `get_tossd` delivers as a nullable integer arrives
   here as a string:

   ```python
   raw["provider"].dtype
   ```

   ```text
   <StringDtype(na_value=nan)>
   ```

   ```python
   raw.loc[5, "provider"]
   ```

   ```text
   '4'
   ```

4. **Query the same year with `get_tossd` and compare.** Same rows, a
   fifth of the columns with the `"minimal"` preset, and typed codes:

   ```python
   h = tossd.get_tossd(years=2024, columns="minimal")
   h.shape
   ```

   ```text
   (474026, 19)
   ```

   ```python
   h["provider_code"].dtype
   ```

   ```text
   Int16Dtype()
   ```

   ```python
   int(h.loc[5, "provider_code"])
   ```

   ```text
   4
   ```

   `raw.loc[5, "provider"]` and `h.loc[5, "provider_code"]` carry the same
   code, `4`, one as the string `'4'` and one as the integer `4`.

## Verify it worked

`get_tossd_raw` applies no row filters and no unit conversion.

No provider filter runs, so the aggregate pseudo-provider's rows (code `0`)
are still in the frame, same count as `get_tossd` reports for the same year:

```python
int((raw["provider"] == "0").sum())
```

```text
5626
```

No unit conversion runs, so an amount matches `get_tossd`'s own default
(`units="usd_thousand"`) exactly:

```python
float(raw.loc[5, "USD_disbursements"])
```

```text
10.815487778498811
```

```python
float(h.loc[5, "usd_disbursement"])
```

```text
10.815487778498811
```

`get_tossd_raw` also leaves the publisher's empty strings as empty strings.
`get_tossd` turns them into real nulls:

```python
int((raw["ProjectNumber"] == "").sum())
```

```text
41069
```

```python
int(h["project_number"].isna().sum())
```

```text
41069
```

<!-- prettier-ignore -->
!!! warning "Heads up"
    A frame from `get_tossd_raw` has no `is_aggregate` column, no `unit`
    column, and no filtering by provider, recipient, or pillar. Filter and
    convert units yourself with pandas, or query `get_tossd` instead for
    typed columns, the derived `is_aggregate` flag, and built-in filters.

## Troubleshooting

**`TypeError` naming an unexpected keyword argument.** `get_tossd_raw` takes
`years` and `refresh` only:

```python
tossd.get_tossd_raw(years=2024, providers="Senegal")
```

```text
TypeError: get_tossd_raw() got an unexpected keyword argument 'providers'
```

There's no `providers=`, `recipients=`, `pillars=`, or `columns=` on this
function. Filter the returned frame in pandas by the publisher's own column
names (`raw[raw["provider"] == "4"]`), or switch to `get_tossd`, which
takes all four.

## See also

- [Query reference](../reference/query.md) for `get_tossd_raw`'s full
  signature alongside `get_tossd`'s filter and preset contract.
- [Columns, presets, and units](../reference/columns.md) for the full
  renaming table, the dtype for every column, and what counts as schema
  drift.
