# How to measure Pillar II expenditures in the provider country

Filter a Pillar II frame to the sector-code carve-out for spending recorded inside the provider country, then take its share of Pillar II disbursements.

## Steps

1. **Query Pillar II with the `"analysis"` column preset.** `pillar2_provider_costs` reads `sector_code`, which ships in `"analysis"` but not `"minimal"`.

   ```python
   import tossd_reader as tossd

   p2 = tossd.get_tossd(years=2024, pillars=2, columns="analysis", units="usd_million")
   p2.shape
   ```

   ```text
   (155908, 44)
   ```

2. **Filter to the provider-costs carve-out.** It holds two sectors: `910` ("Administrative Costs of Donors") and `930` ("Domestic expenditures for refugees/asylum seekers").

   ```python
   pc = tossd.pillar2_provider_costs(p2)
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
   round(pc["usd_disbursement"].sum() / p2["usd_disbursement"].sum() * 100, 1)
   ```

   ```text
   35.6
   ```

That's 47,503.8 of 133,561.8 USD million. The largest providers, aggregate rows excluded:

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
!!! warning "Sector 720 humanitarian aid is excluded"

    `pillar2_provider_costs` applies a sector-family heuristic. TOSSD's Reporting Instructions describe this category as "expenditures in the provider country". Sector families 910 and 930 are the two that match that description, and 35.6% is this package's estimate on that basis. Sector `910` is a proxy for provider administrative overhead. Most of that spending stays inside the provider country, and some is incurred in-country at the recipient end. Sector `720` ("Humanitarian Assistance") rows are in-country humanitarian aid delivered by agencies such as UNHCR and UNICEF, so they fall outside the carve-out.

## Verify it worked

`pc` is a strict subset of `p2`, restricted to sectors `910` and `930`:

```python
len(pc) < len(p2), [int(c) for c in pc["sector_code"].unique()]
```

```text
(True, [910, 930])
```

## Troubleshooting

**`ValueError` naming `sector_code`.** `pillar2_provider_costs` needs `sector_code` on the frame it's given. That column ships in `"analysis"` and `"all"`, not `"minimal"`. Re-query with `columns="analysis"`, or add `"sector_code"` to an explicit `columns=` list.

## See also

- [Helpers reference](../reference/helpers.md) for `pillar2_provider_costs`'s full contract.
- [Pillars and aggregates](../about/pillars-and-aggregates.md) for the provider-costs carve-out as a concept, and why aggregate rows are excluded from the provider ranking above.
