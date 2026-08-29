# How to split disbursements across SDG goals

Turn a `get_tossd` frame into per-goal disbursement totals, with
multi-tagged activities split so the weighted amounts renormalise to
each activity's original disbursement.

## Steps

1. **Query with the `"analysis"` column preset.** `explode_sdg` reads
   `sdg_codes_raw`, which ships in `"analysis"` but not `"minimal"`.

   ```python
   import tossd_reader as tossd

   sen_a = tossd.get_tossd(
       years=2024, recipients="Senegal", columns="analysis", units="usd_million"
   )
   ```

2. **Explode the SDG codes.** `sdg_codes_raw` packs one or more
   `;`-delimited codes per activity, goals (`4`) and targets (`4.1`)
   mixed together. `explode_sdg` gives each code its own row and adds a
   `sdg_weight` of `1/n` for the `n` codes that row carried.

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

   `sdg_goal` is the code's integer goal part, so a target like `4.1`
   and a goal-level tag like `4` group together.

3. **Sum `usd_disbursement * sdg_weight`, grouped by `sdg_goal`.** The
   weighted amounts for one activity's codes sum back to that
   activity's original disbursement.

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
!!! warning "SDG goal totals do not sum to recipient total"
    Activities with no SDG tag (`sdg_codes_raw` empty or null) are
    dropped from `sdg`, so the goal totals above sum to the SDG-tagged
    subset of `sen_a`. On this
    Senegal 2024 slice the tagged subset is 65.4% of the frame's
    disbursements.

## Verify it worked

Check the tagged share directly.

```python
round(sdg["usd_weighted"].sum() / sen_a["usd_disbursement"].sum() * 100, 1)
```

```text
65.4
```

## Troubleshooting

**`ValueError` naming `sdg_code`, `sdg_goal`, `sdg_is_target`, or
`sdg_weight`.** `explode_sdg` refuses a frame that already carries one
of its own output columns, so a second pass can't silently duplicate
them. Pass it the original `get_tossd` frame, not an earlier
`explode_sdg` result.

## See also

- [Helpers reference](../reference/helpers.md) for `explode_sdg`'s full
  contract, and the other helpers that operate on `get_tossd` output.
- [Columns, presets, and units](../reference/columns.md) for what each
  preset carries and how to pick between them.
