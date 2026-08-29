# How to rank providers by disbursement

Rank providers by disbursement with the aggregate pseudo-provider excluded
and the two-code provider names kept apart.

## Steps

1. **Query the year, with amounts in USD million.**

   ```python
   import tossd_reader as tossd

   h = tossd.get_tossd(years=2024, columns="minimal", units="usd_million")
   ```

2. **Exclude `is_aggregate` before you group.** Left in, provider code `0`,
   the aggregate pseudo-provider, outranks every real provider:

   ```python
   # ❌ aggregate row included, ranks first at 99379.6
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

3. **Group by `["provider_code", "provider_name"]`, sum, and sort.**
   Grouping by `provider_name` alone merges two provider codes together for
   "African Development Bank Group" and "Inter-American Development Bank
   Group". Keying on `provider_code` too keeps them apart:

   ```python
   # ✅ aggregate excluded, codes kept apart
   h[~h["is_aggregate"]].groupby(["provider_code", "provider_name"], observed=True)[
       "usd_disbursement"
   ].sum().sort_values(ascending=False).round(1).head(5)
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

Check what excluding `is_aggregate` dropped, the aggregate rows' share of
the unfiltered total:

```python
agg = h[h["is_aggregate"]]["usd_disbursement"].sum()
total = h["usd_disbursement"].sum()
round(agg / total * 100, 1)
```

```text
20.0
```

## See also

- [Pillars and aggregate rows](../about/pillars-and-aggregates.md) for what
  the aggregate provider is and when to include it.
- [Query reference](../reference/query.md) for `get_tossd`'s full argument
  and preset contract.
