# How to split disbursements across SDG goals

Turn a `get_tossd` frame into per-goal disbursement totals, with multi-tagged activities split so the weighted amounts renormalise to each activity's original disbursement.

## Steps

1. **Query with the `"analysis"` column preset.** `explode_sdg` reads `sdg_codes_raw`, which ships in the `"analysis"` preset. The `"minimal"` preset omits it.

   ```python
   import tossd_reader as tossd

   sen_a = tossd.get_tossd(
       years=2024, recipients="Senegal", columns="analysis", units="usd_million"
   )
   ```

2. **Explode the SDG codes.** `sdg_codes_raw` packs one or more semicolon-delimited codes per activity, combining goals (`4`) and targets (`4.1`). Under the TOSSD Reporting Instructions, activities report up to 10 SDG focus areas. `explode_sdg` gives each code its own row and assigns an equal weight `sdg_weight` of `1/n` across the `n` reported codes.

   ```python
   sdg = tossd.explode_sdg(sen_a)
   sdg[["sdg_code", "sdg_goal", "sdg_is_target", "sdg_weight"]].head()
   ```

   ```text
     sdg_code  sdg_goal  sdg_is_target  sdg_weight
   0      5.1         5           True    0.333333
   1        4         4          False    0.333333
   2        3         3          False    0.333333
   3      4.1         4           True    0.333333
   4       10        10          False    0.333333
   ```

   `sdg_goal` extracts the integer goal number, grouping target-level tags like `4.1` and goal-level tags like `4` under goal 4.

3. **Sum `usd_disbursement * sdg_weight`, grouped by `sdg_goal`.** The weighted amounts for an activity's reported codes sum back to that activity's total disbursement.

   ```python
   sdg["usd_weighted"] = sdg["usd_disbursement"] * sdg["sdg_weight"]
   sdg.groupby("sdg_goal", observed=True)["usd_weighted"].sum().sort_values(
       ascending=False
   ).round(1).head(8)
   ```

   ```text
   sdg_goal
   17    348.8
   10    187.7
   5     141.0
   11    138.7
   16    124.7
   3     119.2
   4     111.5
   2      94.7
   Name: usd_weighted, dtype: float64
   ```

<!-- prettier-ignore -->
!!! warning "Heads up"
    Activities with no SDG tag (`sdg_codes_raw` empty or null) drop out of `sdg`. Goal totals sum to the SDG-tagged subset of `sen_a`. On this Senegal 2024 query, tagged activities account for 65.4% of total disbursements.

## Verify it worked

Check the tagged share directly.

```python
round(sdg["usd_weighted"].sum() / sen_a["usd_disbursement"].sum() * 100, 1)
```

```text
65.4
```

## Troubleshooting

**`ValueError` naming `sdg_code`, `sdg_goal`, `sdg_is_target`, or `sdg_weight`.** `explode_sdg` rejects frames that already contain its output columns to prevent accidental duplicate weighting. Pass the original `get_tossd` frame.

## See also

- [Helpers reference](../reference/helpers.md) for `explode_sdg` parameter definitions and weighting rules.
- [Columns, presets, and units](../reference/columns.md) for columns included in the `"analysis"` preset.
