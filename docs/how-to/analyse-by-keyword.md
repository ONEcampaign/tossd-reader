# How to measure climate and gender finance with keyword markers

Tag a `get_tossd` frame with the twelve packaged keyword markers, then total disbursement per marker, or combine several, without double-counting activities tagged for more than one.

## Steps

1. **Query with the `"analysis"` column preset.** `extract_keywords` and `keyword_totals` both read `keywords_raw`, which ships in the `"analysis"` preset. The `"minimal"` preset omits it.

   ```python
   import tossd_reader as tossd

   df = tossd.get_tossd(years=2024, columns="analysis", units="usd_million")
   ```

2. **Add the marker columns for row-level work.** `extract_keywords` adds one boolean `kw_<marker>` column per marker, including `kw_gender`, `kw_adaptation`, and `kw_mitigation`. Select rows with a boolean mask when the task needs the matching rows themselves and not just a total, for example breaking a marker down by another dimension.

   ```python
   kw = df.tossd.extract_keywords()
   gender = kw[kw.kw_gender]
   gender.groupby("recipient_name", observed=True)["usd_disbursement"].sum().sort_values(
       ascending=False
   ).round(1).head(3)
   ```

   ```text
   recipient_name
   Developing countries, unspecified    9080.0
   India                                7420.9
   Indonesia                            3874.6
   Name: usd_disbursement, dtype: float64
   ```

3. **Total disbursement per marker with `df.tossd.keyword_totals(markers=…)`, without double-counting activities tagged for more than one.** It recomputes marker masks from `keywords_raw` internally and adds a final `"Combined"` row, the union of every requested marker's mask.

   ```python
   df.tossd.keyword_totals(markers=["adaptation", "mitigation"])
   ```

   ```text
          marker  usd_disbursement  n_rows
   0  adaptation      38414.214244   41524
   1  mitigation      61608.343767   34279
   2    Combined      78643.461436   53822
   ```

   The marker rows sum to 100,022.6 million, more than `"Combined"`'s 78,643.5. A row tagged for both adaptation and mitigation counts once under each marker row but only once in `"Combined"`, the honest total for climate finance.

   `n_rows` counts matching rows, not distinct activities. The publisher can split one activity across several rows, and those rows can carry different keyword tags from each other, so a multi-row activity may count more than once here. Omit `markers=` for all twelve packaged markers plus `"Combined"`.

<!-- prettier-ignore -->
!!! warning "Heads up"
    The twelve markers are independent booleans without weights or partitioning. Marker totals overlap by design. The vocabulary is a fixed twelve. An absent marker indicates the activity is untagged.

## Verify it worked

Sum the twelve marker counts and compare against the number of rows carrying at least one marker.

```python
kw_cols = [c for c in kw.columns if c.startswith("kw_")]
print(kw[kw_cols].sum().sum())
```

```text
258001
```

```python
print(kw[kw_cols].any(axis=1).sum())
```

```text
170206
```

The 258,001 marker instances span 170,206 rows. The gap is rows carrying more than one marker, the same overlap `keyword_totals()`'s `"Combined"` row accounts for.

## Troubleshooting

**`ValueError` naming `keywords_raw`.** `extract_keywords` and `keyword_totals` both require it. That column ships in the `"analysis"` and `"all"` presets. The `"minimal"` preset omits it.

```python
tossd.get_tossd(years=2024, columns="minimal").tossd.keyword_totals()
```

```text
ValueError: keyword_totals() needs column(s) keywords_raw, not present in df. Re-query with columns='analysis', or add keywords_raw to your columns= list.
```

**`ValueError` naming a `markers=` value.** `keyword_totals` rejects a name it doesn't recognise and names the closest matches.

```python
df.tossd.keyword_totals(markers="adaptaion")
```

```text
ValueError: keyword_totals() marker 'adaptaion' not recognised; expected one of adaptation, biodiversity, covid_19, gender, idps_hostcommunities, mitigation, non_17_3_1, ppr_preparedness, ppr_response, refugees_hostcommunities, transnational_benefits_global, voluntaryrefugeereturn_reintegration. Closest matches: adaptation.
```

## See also

- [Helpers reference](../reference/helpers.md) for `extract_keywords` parameter details and the complete marker vocabulary.
- [Columns, presets, and units](../reference/columns.md) for columns included in `"analysis"`.
