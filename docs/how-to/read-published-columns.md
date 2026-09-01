# How to read the published columns unchanged

Call `get_tossd_raw` to get a year of TOSSD data with the publisher's original column names, dtypes, and ordering across every row.

<!-- prettier-ignore -->
!!! info "Why"
    Three practical reasons to use `get_tossd_raw`:

    - Inspecting raw published records directly before relying on normalised columns.
    - Isolating specific values when diagnosing a `SchemaDriftError`, which triggers during normalisation.
    - Reconciling totals against the International Forum on TOSSD (IFT) portal at tossd.online, which displays raw published headers and amounts.

## Steps

1. **Query the year with `get_tossd_raw`.** The function accepts `years` and `refresh` parameters.

   ```python
   import tossd_reader as tossd

   raw = tossd.get_tossd_raw(years=2024)
   raw.shape
   ```

   ```text
   (474026, 53)
   ```

   The resulting frame contains 474,026 rows, matching the full row count of `get_tossd(years=2024)`, across all 53 original published columns.

2. **Inspect the column names.** The frame retains the publisher's unrenamed headers.

   ```python
   list(raw.columns[:10])
   ```

   ```text
   ['Year', 'provider', 'ProviderNameE', 'agencyname_E', 'tossdid', 'ProjectNumber', 'recipientcode', 'recipientnamee', 'regionnamee', 'Channel']
   ```

   The first three columns correspond to `year`, `provider_code`, and `provider_name` in `get_tossd`.

3. **Check the data types.** Every column is stored as `str` or `float64`, representing the direct output of parquet reading without schema casting.

   ```python
   raw.dtypes.value_counts()
   ```

   ```text
   str        44
   float64     9
   Name: count, dtype: int64
   ```

   A code column delivered as a nullable integer in `get_tossd` remains a string in the raw frame.

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

4. **Query the same year with `get_tossd` to compare.** `get_tossd` returns the same rows with typed columns and a focused set under the `"minimal"` preset.

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

   `raw.loc[5, "provider"]` and `h.loc[5, "provider_code"]` hold the same provider code (4), represented respectively as a string and an integer.

## Verify it worked

`get_tossd_raw` delivers unfiltered rows in the publisher's original units.

Without provider filtering, the aggregate pseudo-provider rows (code `0`) remain in the frame, matching the count in `get_tossd` for the same year.

```python
int((raw["provider"] == "0").sum())
```

```text
5626
```

Amounts remain in the publisher's original scale, matching `get_tossd`'s default of `units="usd_thousand"`.

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

`get_tossd_raw` preserves empty strings from the source file, whereas `get_tossd` converts them to nulls.

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
    A frame from `get_tossd_raw` provides only the raw published columns. Filter and convert units in pandas, or query `get_tossd` to get typed columns, the derived `is_aggregate` flag, and built-in filters.

## Troubleshooting

**`TypeError` naming an unexpected keyword argument.** Passing filter arguments such as `providers=` or `recipients=` to `get_tossd_raw` raises a `TypeError`.

```python
tossd.get_tossd_raw(years=2024, providers="Senegal")
```

```text
TypeError: get_tossd_raw() got an unexpected keyword argument 'providers'
```

The function accepts only `years` and `refresh`. To filter by provider, recipient, pillar, or custom columns, filter the returned frame in pandas using publisher column names, or use `get_tossd`.

## See also

- [Query reference](../reference/query.md) for `get_tossd_raw`'s full signature alongside `get_tossd`'s filter and preset contract.
- [Columns, presets, and units](../reference/columns.md) for the complete column renaming table, data types, and schema drift handling.
