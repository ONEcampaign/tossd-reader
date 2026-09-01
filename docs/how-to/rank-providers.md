# How to rank providers by disbursement

Rank official providers by total disbursement, using the `is_aggregate` flag to separate provider activities from aggregate totals and grouping by provider code and name.

## Steps

1. **Query activity records with amounts scaled to USD million.**

   ```python
   import tossd_reader as tossd

   h = tossd.get_tossd(years=2024, columns="minimal", units="usd_million")
   ```

   The `columns="minimal"` preset provides `provider_code`, `provider_name`, `is_aggregate`, and `usd_disbursement`.

2. **Filter out aggregate total rows.** The TOSSD data published at tossd.online includes summary aggregate records alongside activity records. Grouping without filtering aggregates inflates totals with double-counted figures.

   ```python
   # Unfiltered data includes aggregate summary rows
   h.groupby("provider_name", observed=True)["usd_disbursement"].sum().sort_values(
       ascending=False
   ).round(1).head(3)
   ```

   ```text
   provider_name
   Aggregate          99379.6
   United States      67695.9
   EU Institutions    58667.5
   Name: usd_disbursement, dtype: float64
   ```

3. **Group by `["provider_code", "provider_name"]` and sort descending.** Grouping by both `provider_code` and `provider_name` ensures distinct reporting entities that share similar labels remain separate.

   ```python
   # Filter aggregates and group by code and name
   ranked = (
       h[~h["is_aggregate"]]
       .groupby(["provider_code", "provider_name"], observed=True)["usd_disbursement"]
       .sum()
       .sort_values(ascending=False)
       .round(1)
   )
   ranked.head(5)
   ```

   ```text
   provider_code  provider_name               
   302            United States                   67695.9
   918            EU Institutions                 58667.5
   4              France                          25444.6
   915            Asian Development Bank Group    18558.3
   701            Japan                           17339.4
   Name: usd_disbursement, dtype: float64
   ```

## Verify it worked

Calculate the share of disbursements represented by aggregate rows to confirm the scale of separated totals.

```python
agg = h[h["is_aggregate"]]["usd_disbursement"].sum()
total = h["usd_disbursement"].sum()
round(agg / total * 100, 1)
```

```text
20.0
```

Aggregate summary rows account for 20.0% of the total recorded disbursements in the 2024 dataset.

## See also

- [Pillars and aggregate rows](../about/pillars-and-aggregates.md) for how aggregate rows are constructed and reported in TOSSD.
- [Query reference](../reference/query.md) for query arguments and column presets.
