# How to analyse activities by SDG

Turn a `get_tossd` frame into per-SDG-goal disbursement totals, with
multi-tagged activities split so the totals renormalise correctly.

## Steps

1. **Query with the `"analysis"` column preset.** `explode_sdg` reads
   `sdg_codes_raw`. That column ships in `"analysis"`. `"minimal"` doesn't
   carry it.

   ```python
   import tossd_reader as tossd

   sen_a = tossd.get_tossd(
       years=2024, recipients="Senegal", columns="analysis", units="usd_million"
   )
   ```

2. **Explode the SDG codes.** `sdg_codes_raw` packs one or more
   `;`-delimited codes per activity, goals (`4`) and targets (`4.1`) mixed
   together. `explode_sdg` gives each code its own row:

   ```python
   sdg = tossd.explode_sdg(sen_a)
   ```

   ```text
   len(sen_a), len(sdg)
   (4802, 10640)
   ```

   ```python
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

   An activity tagged with three codes turns into three rows, each carrying
   `sdg_weight = 1/3`. `sdg_goal` is the code's integer goal part, so a
   target like `4.1` and a goal-level tag like `4` group together.

3. **Sum `usd_disbursement * sdg_weight`, grouped by `sdg_goal`.** Each
   weighted row carries a fraction of the activity's amount. An activity
   split across 3 codes contributes a third of its amount to each of the
   three rows, and the three weighted amounts sum back to the activity's
   original disbursement.

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

!!! warning "Heads up"

    Activities with no SDG tag (`sdg_codes_raw` empty or null) are dropped
    from `sdg`, so they contribute nothing to any goal total. The per-goal
    totals above sum to the SDG-tagged subset of `sen_a`, not to
    `sen_a["usd_disbursement"].sum()`. On this Senegal 2024 slice the tagged
    subset is 65.4% of the frame's disbursements.

## Verify it worked

Row count should grow (one input row becomes `n` output rows for an
activity with `n` codes), and the tagged share should be a fraction, not
all, of the frame:

```python
len(sen_a), len(sdg)
```

```text
(4802, 10640)
```

```python
round(sdg["usd_weighted"].sum() / sen_a["usd_disbursement"].sum() * 100, 1)
```

```text
65.4
```

## Troubleshooting

**`ValueError` naming `sdg_code`, `sdg_goal`, `sdg_is_target`, or
`sdg_weight`.** `explode_sdg` refuses a frame that already carries one of
its own output columns, to avoid silently duplicating them on a second
pass. Pass it the original `get_tossd` frame, not the output of an earlier
`explode_sdg` call.

## See also

- [Helpers reference](../reference/helpers.md) for `explode_sdg`'s full
  contract, and the other helpers that operate on `get_tossd` output.
- [Columns, presets, and units](../reference/columns.md) for what each
  preset carries and how to pick between them.
