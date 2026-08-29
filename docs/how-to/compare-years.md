# How to compare TOSSD totals across years

Compare a multi-year TOSSD total in constant prices, and check which known discontinuities fall inside the years you're comparing.

## Steps

1. **Pull the years you want to compare.** Use `range` for a span.

   ```python
   import tossd_reader as tossd

   df = tossd.get_tossd(
       years=range(2019, 2025),
       columns=["year", "usd_disbursement", "usd_disbursement_deflated"],
       units="usd_million",
   )
   ```

An explicit `columns=` list only forces in `tossd_pillar`, `tossd_subpillar`, `is_aggregate`, and `unit`. Name `"year"` explicitly to avoid a `KeyError` during groupby.

2. **Group by year and sum both the current-price and the `_deflated` column.** Every amount column has a `_deflated` twin, holding the same amount restated in constant prices.

   ```python
   df.groupby("year", observed=True)[
       ["usd_disbursement", "usd_disbursement_deflated"]
   ].sum().round(1)
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

Global 2019-2024 disbursements rise 66.0% in current prices and 46.3% in constant prices. The 20-point gap is price inflation.

3. **Check `get_structural_breaks()` for rows that intersect the window.** It is a curated reference table. You read it and cite it alongside a figure.

   ```python
   breaks = tossd.get_structural_breaks()
   window = breaks[(breaks["break_year"] <= 2024) & (breaks["end_year"] >= 2019)]
   len(window)
   ```

   ```text
   4
   ```

Four rows intersect 2019 to 2024: two on the sub-pillar rollout, one on modality code K02, one on the reporter base. [Why TOSSD totals rise](../about/comparability.md) prints the table and reads each row.

## Verify it worked

Count distinct `provider_code` values per year, excluding the aggregate pseudo-provider.

```python
counts = tossd.get_tossd(years=range(2019, 2025), columns=["year", "provider_code"])
counts[counts["provider_code"] != 0].groupby("year", observed=True)[
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

97 rising to 130 matches the `reporters` row above.

## See also

- [Why TOSSD totals rise](../about/comparability.md) for the reporter base, the sub-pillar rollout, and what the breaks table is for.
- [About the amount columns](../about/amounts.md) for current versus constant prices and the rest of the `usd_*` columns.
