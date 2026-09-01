# How to measure climate and gender finance with keyword markers

Tag a `get_tossd` frame with the twelve packaged keyword markers, then select the rows that match one marker, or several, without double-counting.

## Steps

1. **Query with the `"analysis"` column preset.** `extract_keywords` reads `keywords_raw`, which ships in the `"analysis"` preset. The `"minimal"` preset omits it.

   ```python
   import tossd_reader as tossd

   sen_a = tossd.get_tossd(
       years=2024, recipients="Senegal", columns="analysis", units="usd_million"
   )
   ```

2. **Add the marker columns.** `extract_keywords` adds one boolean `kw_<marker>` column per marker, including `kw_gender`, `kw_adaptation`, and `kw_mitigation`.

   ```python
   kw = tossd.extract_keywords(sen_a)
   ```

3. **Select rows with a boolean mask.** A single marker filters by its column.

   ```python
   gender = kw[kw.kw_gender]
   round(gender["usd_disbursement"].sum(), 1)
   ```

   ```text
   556.3
   ```

   Gender-focused activities represent 556.3 of Senegal's 2,648.0 USD million total (21.0%), across 1,308 activities. For climate finance, take the union of adaptation and mitigation to avoid double-counting activities tagged for both.

   ```python
   # Union of the two masks: dual-tagged activities are counted once
   climate = kw[kw.kw_adaptation | kw.kw_mitigation]
   round(climate["usd_disbursement"].sum(), 1)  # 432.5

   # Summing separate totals double-counts dual-tagged activities
   round(
       kw[kw.kw_adaptation]["usd_disbursement"].sum()
       + kw[kw.kw_mitigation]["usd_disbursement"].sum(),
       1,
   )  # 496.6
   ```

<!-- prettier-ignore -->
!!! warning "Heads up"
    The twelve markers are independent booleans without weights or partitioning. Marker totals overlap. Present each marker total independently. The vocabulary is a fixed twelve. An absent marker indicates the activity is untagged.

## Verify it worked

Sum the twelve marker counts and compare against the number of activities carrying at least one marker.

```python
kw_cols = [c for c in kw.columns if c.startswith("kw_")]
kw[kw_cols].sum().sum()
```

```text
2950
```

```python
kw[kw_cols].any(axis=1).sum()
```

```text
1819
```

The 2,950 marker instances map to 1,819 distinct activities because dual-tagged projects carry multiple markers simultaneously.

## Troubleshooting

**`ValueError` naming `keywords_raw`.** `extract_keywords` requires `keywords_raw` on the input frame. That column ships in the `"analysis"` and `"all"` presets. The `"minimal"` preset omits it. Re-query with `columns="analysis"` or add `"keywords_raw"` to an explicit `columns=` list.

## See also

- [Helpers reference](../reference/helpers.md) for `extract_keywords` parameter details and the complete marker vocabulary.
- [Columns, presets, and units](../reference/columns.md) for columns included in `"analysis"`.
