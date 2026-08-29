# How to measure climate and gender finance with keyword markers

Tag a `get_tossd` frame with the twelve packaged keyword markers, then select the rows that match one marker, or several, without double-counting.

## Steps

1. **Query with the `"analysis"` column preset.** `extract_keywords` reads `keywords_raw`, which ships in `"analysis"` but not `"minimal"`.

   ```python
   import tossd_reader as tossd

   sen_a = tossd.get_tossd(
       years=2024, recipients="Senegal", columns="analysis", units="usd_million"
   )
   ```

2. **Add the marker columns.** `extract_keywords` adds one boolean `kw_<marker>` column per marker, for example `kw_gender`, `kw_adaptation`, `kw_mitigation`.

   ```python
   kw = tossd.extract_keywords(sen_a)
   ```

3. **Select rows with a boolean mask.** A single marker is one column.

   ```python
   gender = kw[kw.kw_gender]
   round(gender["usd_disbursement"].sum(), 1)
   ```

   ```text
   556.3
   ```

556.3 USD million of Senegal's 2,648.0 total (21.0%), across 1,308 activities. Climate finance is the union of the two markers.

   ```python
   # ✅ union of the two masks, dual-tagged activities counted once
   climate = kw[kw.kw_adaptation | kw.kw_mitigation]
   round(climate["usd_disbursement"].sum(), 1)  # 432.5

   # ❌ adding the two marker totals double-counts dual-tagged activities
   round(
       kw[kw.kw_adaptation]["usd_disbursement"].sum()
       + kw[kw.kw_mitigation]["usd_disbursement"].sum(),
       1,
   )  # 496.6
   ```

<!-- prettier-ignore -->
!!! warning "Overlapping marker totals"
    The twelve markers are independent booleans with no weight column and no partition. Marker totals overlap. Present each marker total independently. The vocabulary is a fixed twelve. An absent marker means the activity is untagged.

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

2,950 marker instances land on 1,819 tagged activities, because a dual-tagged activity carries more than one marker at once.

## Troubleshooting

**`ValueError` naming `keywords_raw`.** `extract_keywords` needs `keywords_raw` on the frame it's given. That column ships in `"analysis"` and `"all"`, not `"minimal"`. Re-query with `columns="analysis"`, or add `"keywords_raw"` to an explicit `columns=` list.

## See also

- [Helpers reference](../reference/helpers.md) for `extract_keywords`'s full contract, including the fixed marker vocabulary.
- [Columns, presets, and units](../reference/columns.md) for what `"analysis"` carries, including `keywords_raw`.
