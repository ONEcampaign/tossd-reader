# How to measure Pillar II expenditures in the provider country

Filter a Pillar II frame to the sector-code carve-out for spending recorded inside the provider country, then calculate its share of total Pillar II disbursements.

## Steps

1. **Query Pillar II with the `"analysis"` column preset.** `filter_provider_costs` reads `sector_code`, which ships in the `"analysis"` preset. The `"minimal"` preset omits it.

   ```python
   import tossd_reader as tossd

   p2 = tossd.get_tossd(years=2024, pillars=2, columns="analysis", units="usd_million")
   p2.shape
   ```

   ```text
   (155908, 44)
   ```

2. **Filter to the provider-costs carve-out.** The carve-out includes sector 910 ("Administrative Costs of Donors") and sector 930 ("Domestic expenditures for refugees/asylum seekers").

   ```python
   pc = tossd.filter_provider_costs(p2)
   pc.groupby(["sector_code", "sector_name"], observed=True)[
       "usd_disbursement"
   ].sum().round(1)
   ```

   ```text
   sector_code  sector_name
   910          Administrative Costs of Donors                       16826.6
   930          Domestic expenditures for refugees/asylum seekers    30677.2
   Name: usd_disbursement, dtype: float64
   ```

3. **Take the share of Pillar II disbursements.**

   ```python
   print(round(pc["usd_disbursement"].sum() / p2["usd_disbursement"].sum() * 100, 1))
   ```

   ```text
   35.6
   ```

   Provider-country expenditures account for 47,503.8 of 133,561.8 USD million (35.6% of Pillar II in 2024). The five largest providers after removing aggregate rows are shown below.

   ```python
   pc[~pc["is_aggregate"]].groupby("provider_name", observed=True)[
       "usd_disbursement"
   ].sum().sort_values(ascending=False).round(1).head(5)
   ```

   ```text
   provider_name
   United States      14304.2
   United Kingdom      4524.2
   France              2261.5
   Canada              2073.7
   EU Institutions     2012.3
   Name: usd_disbursement, dtype: float64
   ```

<!-- prettier-ignore -->
!!! warning "Heads up"
    `filter_provider_costs` applies a sector-family heuristic. The TOSSD Reporting Instructions issued by the International Forum on TOSSD (IFT) at tossd.online define this category as expenditures in the provider country, coded via modality `H00`. TOSSD does not publish a sector-based carve-out matching that definition. Sector families 910 and 930 approximate it, producing this package's 35.6% estimate. In the 2024 data, sector-910/930 rows and modality-H00 rows overlap in a single row. Sector 910 acts as a proxy for provider administrative overhead. Most administrative spending remains inside the provider country, while some occurs in recipient countries. Sector 700 ("Humanitarian Assistance") represents field humanitarian aid delivered through agencies like UNHCR and UNICEF, so it falls outside this carve-out.

## Verify it worked

`pc` is a subset of `p2` restricted to sectors 910 and 930.

```python
len(pc) < len(p2), [int(c) for c in pc["sector_code"].unique()]
```

```text
(True, [910, 930])
```

## Troubleshooting

**`ValueError` naming `sector_code`.** `filter_provider_costs` requires `sector_code` on the input frame. That column ships in the `"analysis"` and `"all"` presets. The `"minimal"` preset omits it. Re-query with `columns="analysis"` or add `"sector_code"` to an explicit `columns=` list.

## See also

- [Helpers reference](../reference/helpers.md) for `filter_provider_costs` parameter definitions and behaviour.
- [Pillars and aggregates](../about/pillars-and-aggregates.md) for the provider-costs carve-out concept and aggregate row filtering.
