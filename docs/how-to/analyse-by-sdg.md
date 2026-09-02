# How to split disbursements across SDG goals

Calculate per-goal or per-target disbursement totals from a `get_tossd` frame, weighted so activities tagged with multiple SDG codes count fractionally across each goal.

## Steps

1. **Query data using the `"analysis"` column preset.** Both `sdg_totals` and `explode_sdg` read `sdg_codes_raw`, which is included in the `"analysis"` preset. The `"minimal"` preset omits it.

    ```python
    import tossd_reader as tossd

    df = tossd.get_tossd(years=2024, columns="analysis", units="usd_million")
    ```

2. **Explode SDG codes for row-level analysis.** The `sdg_codes_raw` column packs one or more semicolon-delimited codes per activity, combining goals (`4`) and targets (`4.2`). The TOSSD Reporting Instructions cap dissemination at the first ten SDG targets or goals reported per activity, so activities with more tags show only the first ten. `explode_sdg` gives each code its own row and assigns an equal weight `sdg_weight` of `1/n` across the `n` reported codes. Pass `value=` to generate a precomputed `{value}_weighted` column alongside the untouched original.

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

    The `sdg_goal` column extracts the integer goal number, grouping target-level tags like `4.2` and goal-level tags like `13` under their primary goal. Summing `usd_disbursement_weighted` restores each activity's original disbursement total.

3. **Calculate weighted disbursements per goal with `df.tossd.sdg_totals()`.** This method runs the explode-and-weight process internally, allocating a multi-tagged activity's disbursement proportionally across its goals. It excludes `is_aggregate` rows by default (`include_aggregates=False`).

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

    The `share_pct` column reports each goal's share of the weighted total (0-100, unrounded) and sums to 100 across the full result before applying any `top=` truncation. That weighted total equals the SDG-tagged subset of the included rows' `usd_disbursement`, as activities with no SDG tag (an empty or null `sdg_codes_raw`) contribute zero to goal totals.

    Pass `level="code"` to obtain target-level detail.

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

    The publisher formats some goal-level tags with a trailing `.0` token (`"17.0"`, `"16.0"`, `"1.0"`, `"9.0"` in the 2024 file). Setting `level="code"` preserves each distinct token as its own row. Setting `level="goal"` (the default) folds these into their respective goals alongside standard goal-level tags.

## Verify it worked

Compare the SDG-tagged total to the non-aggregate total in `df`.

```python
tagged = df.tossd.sdg_totals()["usd_disbursement"].sum()
non_aggregate = df.tossd.exclude_aggregates()["usd_disbursement"].sum()
print(round(tagged / non_aggregate * 100, 1))
```

```text
69.2
```

In this dataset, 69.2% of non-aggregate disbursements carry at least one SDG tag. The remainder contain no `sdg_codes_raw` entry.

## Troubleshooting

**`ValueError` naming `sdg_codes_raw`.** Both `sdg_totals` and `explode_sdg` require `sdg_codes_raw`. Re-query with `columns="analysis"` or add `sdg_codes_raw` to your explicit column list.

```python
tossd.get_tossd(years=2024, columns="minimal").tossd.sdg_totals()
```

```text
ValueError: sdg_totals() needs column(s) sdg_codes_raw, not present in df. Re-query with columns='analysis', or add sdg_codes_raw to your columns= list.
```

**`ValueError` naming `sdg_code`, `sdg_goal`, `sdg_is_target`, or `sdg_weight`.** Both `explode_sdg` and `sdg_totals` reject a DataFrame that already contains these columns to prevent duplicate weighting. Pass the original `get_tossd` frame.

## See also

- [Helpers reference](../reference/helpers.md) for `explode_sdg` parameter definitions and weighting rules.
- [Columns, presets, and units](../reference/columns.md) for columns included in the `"analysis"` preset.
