# How to split Pillar II into its sub-pillars

Filter to Pillar II.A or II.B with `pillars=`, check sub-pillar coverage before comparing years, and retrieve all Pillar II rows when tracking general pillar spending.

## Steps

1. **Filter with `pillars=`.** Pillar II.A accepts `21`, `"21"`, or `"II.A"`. Pillar II.B accepts `22`, `"22"`, or `"II.B"`. Matching is case-insensitive, so `"ii.a"` also works. All three forms of II.A return identical rows.

   ```python
   import tossd_reader as tossd

   a1 = tossd.get_tossd(years=2024, pillars=21, columns="minimal", units="usd_million")
   a2 = tossd.get_tossd(years=2024, pillars="21", columns="minimal", units="usd_million")
   a3 = tossd.get_tossd(years=2024, pillars="II.A", columns="minimal", units="usd_million")
   print(a1.shape, a2.shape, a3.shape)
   print(a1.equals(a2), a1.equals(a3))
   ```

   ```text
   (59746, 19) (59746, 19) (59746, 19)
   True True
   ```

   Querying both sub-pillars for 2024 gives their disbursement split across International Public Goods (II.A) and Global Challenges (II.B).

   ```python
   b = tossd.get_tossd(years=2024, pillars="II.B", columns="minimal", units="usd_million")
   print(round(a1["usd_disbursement"].sum(), 1), round(b["usd_disbursement"].sum(), 1))
   ```

   ```text
   76510.1 54782.7
   ```

2. **Check sub-pillar coverage before you compare years.** Sub-pillar tagging rolled out gradually starting in 2023. Measure coverage as the share of Pillar II rows where `tossd_subpillar` is `"21"` or `"22"`. An untagged Pillar II row carries `tossd_subpillar == "2"`, the pillar value itself, so counting non-nulls would report full coverage in every year.

   ```python
   def subpillar_coverage(year):
       p2 = tossd.get_tossd(years=year, pillars=2, columns="minimal", units="usd_million")
       tagged = int(p2["tossd_subpillar"].isin(["21", "22"]).sum())
       rows = int(p2.shape[0])
       return rows, tagged, round(tagged / rows * 100, 1)


   for year in (2023, 2024):
       rows, tagged, pct = subpillar_coverage(year)
       print(f"{year}: {tagged} of {rows} pillar-2 rows tagged ({pct}%)")
   ```

   ```text
   2023: 56026 of 110794 pillar-2 rows tagged (50.6%)
   2024: 154500 of 155908 pillar-2 rows tagged (99.1%)
   ```

   <!-- prettier-ignore -->
   !!! warning "Heads up"
       Cross-year sub-pillar comparisons are clean from 2024 onward. Data for 2023 tags roughly half its Pillar II rows, and untagged activities remain under `tossd_subpillar == "2"`.

3. **Read the two warnings emitted by default-years sub-pillar queries.** When `years=None` (the default), a sub-pillar filter narrows automatically to 2023 onward, and a second warning notes the 2023 coverage gap.

   ```python
   ii_a = tossd.get_tossd(pillars=21, columns="minimal")
   ```

   ```text
   UserWarning: Sub-pillar filters are only meaningful from 2023 onward; narrowing the default years [2019, 2020, 2021, 2022, 2023, 2024] to [2023, 2024]. Pass years= explicitly to request years before 2023 (raises InvalidPillarError for a sub-pillar filter).
   UserWarning: 2023 sub-pillar tagging is incomplete: roughly 49% of 2023 pillar-2 rows carry no sub-pillar tag (the rollout wasn't yet complete that year). Treat 2023 sub-pillar splits as indicative; 2024 onward is complete.
   ```

4. **Passing an explicit pre-2023 year with a sub-pillar filter raises an error.** Automatic narrowing applies only when `years=None`. Specifying an explicit year prior to 2023 alongside a sub-pillar filter raises an `InvalidPillarError`.

   ```python
   tossd.get_tossd(years=2021, pillars="II.A", columns="minimal")
   ```

   ```text
   InvalidPillarError: Sub-pillar filters (pillars=21/'II.A' or 22/'II.B') are not meaningful before 2023; requested year(s) [2021] predate that.
   ```

5. **Retrieve every Pillar II row with `pillars=2`.** This retrieves all Pillar II activities across all available years, including the 2022 baseline records and untagged 2023 rows, without year narrowing or warnings.

   ```python
   p2 = tossd.get_tossd(years=2024, pillars=2, columns="minimal", units="usd_million")
   print(p2.groupby("tossd_subpillar", observed=True)["usd_disbursement"].sum().round(1))
   ```

   ```text
   tossd_subpillar
   21    76510.1
   22    54782.7
   2      2269.1
   Name: usd_disbursement, dtype: float64
   ```

## Verify it worked

The three `tossd_subpillar` groups partition every Pillar II row, so the tagged and untagged counts sum to the total row count.

```python
tagged = p2["tossd_subpillar"].isin(["21", "22"]).sum()
untagged = (p2["tossd_subpillar"] == "2").sum()
int(tagged + untagged) == len(p2)
```

```text
True
```

Pillar II disbursements for 2024 total 133,561.8 USD million. Each group amount above is rounded independently, so summing the three printed values differs by a decimal from the total.

## Troubleshooting

**`InvalidPillarError` naming a year.** You passed `pillars=21`/`22` (or `"II.A"`/`"II.B"`) with an explicit `years=` argument containing years before 2023. Omit `years=` to use the 2023-onward default narrowing, or use `pillars=2` to query all Pillar II rows across any year without sub-pillar splits.

## See also

- [Pillars and aggregate rows](../about/pillars-and-aggregates.md) for the sub-pillar rollout context and reporting instructions.
- [Query reference](../reference/query.md) for `get_tossd`'s full `pillars=` filter options.
