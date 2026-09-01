# How to analyse financial instruments and concessionality

Evaluating debt vulnerabilities and the terms of development finance requires disaggregating financial flows by instrument type (grants, concessional loans, non-concessional loans, and equity) and calculating net resource transfers after debt repayments.

This recipe shows how to classify TOSSD financial instruments with the packaged instrument-groups table and calculate gross versus net disbursements.

## Steps

1. **Query activity records and classify instruments.** `add_instrument_group()` needs `finance_instrument_code` and `concessionality_flag`, both shipped in the `"analysis"` column preset.

   ```python
   import tossd_reader as tossd

   df = tossd.get_tossd(years=2024, columns="analysis", units="usd_million")
   ig = df.tossd.add_instrument_group()
   ```

   The debt-instrument code family (`420`-`425`) splits into `"Concessional Loans"` and `"Non-concessional Loans"` by `concessionality_flag`: `1` reads concessional, `0` reads non-concessional. Every other group (`"Grants"`, `"Equity"`, `"Guarantees"`, `"Hybrid/Mezzanine"`, `"Direct Provider Spending"`, `"Other Instruments"`) is decided by `finance_instrument_code` alone.

2. **Total disbursements by instrument group, keeping the unclassified share visible.**

   ```python
   ig.groupby("instrument_group", dropna=False, observed=True)[
       "usd_disbursement"
   ].sum().round(1)
   ```

   ```text
   Concessional Loans           47194.6
   Direct Provider Spending     49378.8
   Equity                        2796.1
   Grants                      200931.0
   Guarantees                     882.3
   Hybrid/Mezzanine               467.2
   Non-concessional Loans       95923.0
   Other Instruments                8.7
   NaN                         100094.2
   ```

   `NaN` carries about 20% of 2024 disbursements. It combines the pseudo-aggregate rows `get_tossd()` keeps by default (`provider_code == 0`, with no `finance_instrument_code` of their own) and the blank-`concessionality_flag` rows in the debt family, which `add_instrument_group()` can't resolve to concessional or non-concessional. pandas' `groupby` drops `NaN` keys by default, so a plain `.groupby("instrument_group")` silently drops this fifth of the total. Pass `dropna=False`, or exclude aggregates first (next step).

3. **Exclude aggregate rows to shrink the unclassified bucket to its real residual.**

   ```python
   ex = df.tossd.exclude_aggregates()
   ig2 = ex.tossd.add_instrument_group()
   ig2.groupby("instrument_group", dropna=False, observed=True)[
       "usd_disbursement"
   ].sum().round(1)
   ```

   ```text
   Concessional Loans           47194.6
   Direct Provider Spending     49378.8
   Equity                        2796.1
   Grants                      200931.0
   Guarantees                     882.3
   Hybrid/Mezzanine               467.2
   Non-concessional Loans       95923.0
   Other Instruments                8.7
   NaN                            714.6
   ```

   Excluding aggregates first removes the pseudo-aggregate share of `NaN`. What's left is the blank-`concessionality_flag` debt rows alone, USD 714.6 million, about 0.2% of the remaining total. `dropna=False` is still worth keeping as a habit. It surfaces this residual instead of folding it silently into the total.

4. **Calculate net resource transfers after debt repayments.** Subtract `usd_reflow` (principal repayments and capital reflows returned to the provider) from `usd_disbursement` to get the net financial transfer a recipient actually received. Debt vulnerability is a Pillar I question, so narrow to Pillar I activities first.

   ```python
   p1 = tossd.get_tossd(years=2024, pillars=1, columns="analysis", units="usd_million")
   p1 = p1.tossd.exclude_aggregates().tossd.add_instrument_group()

   summary = (
       p1.groupby("instrument_group", dropna=False, observed=True)[
           ["usd_disbursement", "usd_reflow"]
       ]
       .sum()
       .reset_index()
   )
   summary["net_disbursement"] = summary["usd_disbursement"] - summary["usd_reflow"]
   summary["share_of_gross_pct"] = (
       summary["usd_disbursement"] / summary["usd_disbursement"].sum() * 100
   ).round(1)
   print(summary.round(1).to_string(index=False))
   ```

   ```text
           instrument_group  usd_disbursement  usd_reflow  net_disbursement  share_of_gross_pct
         Concessional Loans           47086.4     16356.6           30729.8                17.0
   Direct Provider Spending           13163.5       309.9           12853.7                 4.8
                     Equity            2790.5      1314.7            1475.8                 1.0
                     Grants          116268.9      1973.2          114295.7                42.0
                 Guarantees             882.2       859.3              22.9                 0.3
           Hybrid/Mezzanine             466.3       196.2             270.0                 0.2
     Non-concessional Loans           95190.0     52531.5           42658.5                34.4
          Other Instruments               2.9         0.0               2.9                 0.0
                        NaN             714.6       535.7             178.9                 0.3
   ```

   The published data shows a small reflow against grants too, USD 2.0 billion of the USD 116.3 billion disbursed (under 2%). Don't assume a grant row's net figure matches its gross figure exactly.

   <!-- prettier-ignore -->
   !!! warning "Heads up"
       Do not add `usd_amount_mobilised` directly to `usd_disbursement`. `usd_amount_mobilised` measures private commercial capital mobilised through official interventions such as guarantees and syndicated loans. `usd_disbursement` captures direct official fiscal transfers.

5. **Pin the classification vintage before publishing a number.**

   ```python
   tossd.get_instrument_groups_version()
   ```

   ```text
   'oecd-dac-cl15-2026-09-01/instrument-groups-methodology-v2'
   ```

   This names both the OECD DAC "List 15: Type of finance" fetch date and this project's own group-assignment methodology revision. A `finance_instrument_code` the packaged table doesn't cover raises `UnknownCodeError` instead of folding into `"Other Instruments"`. See Troubleshooting.

## Verify it worked

Confirm the `dropna=False` total reconstructs the frame's own total exactly, then check how much a plain (default) `groupby` would silently drop.

```python
with_na = ig.groupby("instrument_group", dropna=False, observed=True)[
    "usd_disbursement"
].sum()
print(round(with_na.sum(), 1) == round(ig["usd_disbursement"].sum(), 1))
```

```text
True
```

```python
default = ig.groupby("instrument_group", observed=True)["usd_disbursement"].sum()
print(round(default.sum(), 1))
```

```text
397581.8
```

The default drop loses the USD 100.1 billion `NaN` bucket entirely. The grouped total comes out to USD 397,581.8 million against the frame's real USD 497,676.0 million.

## Troubleshooting

- **`ValueError` on `add_instrument_group()` naming missing columns.** The DataFrame was queried with `columns="minimal"` or an explicit list missing `finance_instrument_code`/`concessionality_flag`. Re-query with `columns="analysis"`.

  ```python
  m = tossd.get_tossd(years=2024, columns="minimal", units="usd_million")
  m.tossd.add_instrument_group()
  ```

  ```text
  ValueError: add_instrument_group() needs column(s) finance_instrument_code, concessionality_flag, not present in df. Re-query with columns='analysis', or add finance_instrument_code, concessionality_flag to your columns= list.
  ```

- **`UnknownCodeError` on a `finance_instrument_code` value.** A TOSSD vintage newer than the packaged snapshot carries a code `add_instrument_group()` has no mapping for. It raises rather than grouping the row into `"Other Instruments"`, so a stale package never masks a genuinely new instrument. Check `tossd.get_instrument_groups_version()` against the vintage you're reading, and refresh the packaged codelists (`scripts/refresh_codelists.py`) if a mismatch explains it.

## See also

- [About the amount columns](../about/amounts.md) for `usd_disbursement`, `usd_reflow`, and the eight financial metrics.
- [Pillars and aggregate rows](../about/pillars-and-aggregates.md) for the concessionality benchmark (35% grant element, 5% discount rate) `concessionality_flag` implements.
- [Helpers reference](../reference/helpers.md) for `add_instrument_group()`'s full signature and return contract.
