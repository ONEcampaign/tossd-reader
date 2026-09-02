# How to split disbursements across SDG goals

Turn a `get_tossd` frame into per-goal or per-target disbursement totals, weighted so an activity tagged with more than one SDG code counts fractionally under each rather than in full under all of them.

## Steps

1. **Query with the `"analysis"` column preset.** `sdg_totals` and `explode_sdg` both read `sdg_codes_raw`, which ships in the `"analysis"` preset. The `"minimal"` preset omits it.

   ```python
   import tossd_reader as tossd

   df = tossd.get_tossd(years=2024, columns="analysis", units="usd_million")
   ```

2. **Explode the SDG codes for row-level work.** `sdg_codes_raw` packs one or more semicolon-delimited codes per activity, combining goals (`4`) and targets (`4.2`). The TOSSD Reporting Instructions cap dissemination at the first ten SDG targets or goals reported per activity, so an activity tagged with more than ten still shows only its first ten here. `explode_sdg` gives each code its own row and assigns an equal weight `sdg_weight` of `1/n` across the `n` reported codes. Pass `value=` to get a precomputed `{value}_weighted` sibling column alongside the untouched original.

   ```python
   ex = df.tossd.explode_sdg(value="usd_disbursement")
   ex[
       ["sdg_code", "sdg_goal", "sdg_is_target", "sdg_weight", "usd_disbursement_weighted"]
   ].head()
   ```

   ```text
     sdg_code  sdg_goal  sdg_is_target  sdg_weight  usd_disbursement_weighted
   0      4.2         4           True        0.25                   0.002704
   1       13        13          False        0.25                   0.002704
   2       10        10          False        0.25                   0.002704
   3        1         1          False        0.25                   0.002704
   4        5         5          False        0.50                   0.008104
   ```

   `sdg_goal` extracts the integer goal number, grouping target-level tags like `4.2` and goal-level tags like `13` under their goal. A grouped sum of `usd_disbursement_weighted` renormalises to each activity's original disbursement.

3. **Total weighted disbursement per goal with `df.tossd.sdg_totals()`.** It runs the same explode-and-weight step internally, so a multi-tagged activity's disbursement is split across its goals instead of counted in full under each one. Like the other verbs, it excludes `is_aggregate` rows by default (`include_aggregates=False`).

   ```python
   df.tossd.sdg_totals(top=5)
   ```

   ```text
      sdg_goal  usd_disbursement  share_pct  rank
   0        17      50855.509935  18.453846     1
   1         3      26973.450607   9.787807     2
   2        13      24788.626611   8.995003     3
   3         1      21036.438058   7.633454     4
   4         9      20760.196998   7.533215     5
   ```

   `share_pct` is each goal's share of the weighted total, 0-100 and unrounded, and sums to 100 across the full result before any `top=` truncation. That weighted total equals the SDG-tagged subset of the included rows' `usd_disbursement` and never the grand total, since an activity with no SDG tag at all (an empty or null `sdg_codes_raw`) contributes nothing to any goal.

   Pass `level="code"` for target-level detail instead of goal-level.

   ```python
   df.tossd.sdg_totals(level="code", top=5)
   ```

   ```text
     sdg_code  usd_disbursement  share_pct  rank
   0       17      29297.097592  10.630984     1
   1       13      12618.315801   4.578785     2
   2     17.3      12317.547051   4.469646     3
   3        9       9459.240859   3.432457     4
   4       16       8412.056263   3.052467     5
   ```

   The publisher spells some goal-level tags with a trailing `.0` token (`"17.0"`, `"16.0"`, `"1.0"`, `"9.0"` in the 2024 file), since no real SDG target is numbered `.0`. `level="code"` keeps each as its own row. `level="goal"` (the default) folds it into its goal like any other goal-level tag.

## Verify it worked

Compare the SDG-tagged total to `df`'s non-aggregate total.

```python
tagged = df.tossd.sdg_totals()["usd_disbursement"].sum()
non_aggregate = df.tossd.exclude_aggregates()["usd_disbursement"].sum()
print(round(tagged / non_aggregate * 100, 1))
```

```text
69.2
```

69.2% of `df`'s non-aggregate disbursements carry at least one SDG tag. The rest have no `sdg_codes_raw` entry at all.

## Troubleshooting

**`ValueError` naming `sdg_codes_raw`.** `sdg_totals` and `explode_sdg` both need it.

```python
tossd.get_tossd(years=2024, columns="minimal").tossd.sdg_totals()
```

```text
ValueError: sdg_totals() needs column(s) sdg_codes_raw, not present in df. Re-query with columns='analysis', or add sdg_codes_raw to your columns= list.
```

**`ValueError` naming `sdg_code`, `sdg_goal`, `sdg_is_target`, or `sdg_weight`.** `explode_sdg` and `sdg_totals` both reject a frame that already carries these columns, to prevent accidental duplicate weighting. Pass the original `get_tossd` frame.

## See also

- [Helpers reference](../reference/helpers.md) for `explode_sdg` parameter definitions and weighting rules.
- [Columns, presets, and units](../reference/columns.md) for columns included in the `"analysis"` preset.
