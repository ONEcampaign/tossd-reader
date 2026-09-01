# How to compare TOSSD totals across years

Compare multi-year TOSSD disbursements in constant prices and identify reporting breaks across the comparison window.

## Steps

1. **Query the comparison period with current and deflated amount columns.**

   ```python
   import tossd_reader as tossd

   df = tossd.get_tossd(
       years=range(2019, 2025),
       columns=["year", "usd_disbursement", "usd_disbursement_deflated"],
       units="usd_million",
   )
   ```

   The `get_tossd` function automatically includes `tossd_pillar`, `tossd_subpillar`, `is_aggregate`, and `unit` in custom column lists. Include `"year"` explicitly when grouping by year.

2. **Group by year and sum both current and constant price amounts.** Every financial flow column in `tossd_reader` provides a paired `_deflated` counterpart that expresses amounts in constant prices.

   ```python
   totals = (
       df.groupby("year", observed=True)[["usd_disbursement", "usd_disbursement_deflated"]]
       .sum()
       .round(1)
   )
   totals
   ```

   ```text
         usd_disbursement  usd_disbursement_deflated
   year                                             
   2019          299878.4                   340219.0
   2020          372334.6                   414304.5
   2021          392156.9                   411967.9
   2022          441608.0                   477946.4
   2023          472601.8                   484367.0
   2024          497676.0                   497676.0
   ```

   Between 2019 and 2024, total disbursements increased 66.0% in current prices and 46.3% in constant prices. The remaining gap reflects price inflation.

3. **Inspect known structural breaks across the comparison window.** The International Forum on TOSSD (IFT) expanded reporting coverage and introduced new classifications over successive reporting cycles. The `get_structural_breaks` helper lists these methodological changes.

   ```python
   breaks = tossd.get_structural_breaks()
   window = breaks[(breaks["break_year"] <= 2024) & (breaks["end_year"] >= 2019)]
   len(window)
   ```

   ```text
   4
   ```

   Four structural breaks intersect the 2019 to 2024 window, covering sub-pillar rollouts, modality code expansions, and the growth of the reporter base. See [Why TOSSD totals rise](../about/comparability.md) for details on each break.

4. **Hold reporting providers constant to isolate real growth.** To prevent the addition of 33 new reporting institutions between 2019 and 2024 from distorting multi-year growth rates, filter to entities that reported in all years.

   ```python
   # Identify providers present in all six years
   df_all = tossd.get_tossd(
       years=range(2019, 2025),
       columns=["year", "provider_code", "usd_disbursement_deflated"],
       units="usd_million",
   )
   df_clean = df_all[~df_all["is_aggregate"]]

   all_years = set(range(2019, 2025))
   consistent_providers = (
       df_clean.groupby("provider_code")["year"]
       .nunique()
       .loc[lambda s: s == len(all_years)]
       .index
   )

   cohort_totals = (
       df_clean[df_clean["provider_code"].isin(consistent_providers)]
       .groupby("year", observed=True)["usd_disbursement_deflated"]
       .sum()
       .round(1)
   )
   cohort_totals
   ```

   ```text
   year
   2019    238410.2
   2020    289124.5
   2021    285640.1
   2022    331405.8
   2023    338910.4
   2024    345210.6
   Name: usd_disbursement_deflated, dtype: float64
   ```

## Verify it worked

Count distinct reporting providers per year, separating aggregate rows with `~is_aggregate`.

```python
counts = tossd.get_tossd(years=range(2019, 2025), columns=["year", "provider_code"])
counts[~counts["is_aggregate"]].groupby("year", observed=True)[
    "provider_code"
].nunique()
```

```text
year
2019     97
2020    109
2021    119
2022    129
2023    129
2024    130
Name: provider_code, dtype: int64
```

The provider count expands from 97 in 2019 to 130 in 2024, matching the structural break record for reporting base expansion.

## See also

- [Why TOSSD totals rise](../about/comparability.md) for reporter base changes and sub-pillar history.
- [About the amount columns](../about/amounts.md) for current versus constant prices and financial flow definitions.
