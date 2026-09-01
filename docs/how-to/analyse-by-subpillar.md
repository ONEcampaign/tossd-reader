# How to split Pillar II into its sub-pillars

Filter to Pillar II.A or II.B with `pillars=`, then split Pillar II by sub-pillar and year with `df.tossd.subpillar_breakdown()`. Check sub-pillar coverage before comparing years either way. Two different coverage numbers exist, and they measure different things.

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

2. **Check sub-pillar coverage by row before you compare years.** Sub-pillar tagging rolled out gradually starting in 2023. `tossd_subpillar` is `NA` on any Pillar II row the reporting provider left untagged, so `.notna()` gives the row-share coverage directly. `df.tossd.subpillar_breakdown()` (step 5) reports a related but different number, value-share coverage. Keep the two figures apart when you cite one.

   ```python
   p2 = tossd.get_tossd(years=2023, pillars=2, columns="minimal")
   print(round(p2["tossd_subpillar"].notna().mean() * 100, 1))
   ```

   ```text
   50.6
   ```

   ```python
   p2 = tossd.get_tossd(years=2024, pillars=2, columns="minimal")
   print(round(p2["tossd_subpillar"].notna().mean() * 100, 1))
   ```

   ```text
   99.1
   ```

   <!-- prettier-ignore -->
   !!! warning "Heads up"
       Cross-year sub-pillar comparisons are clean from 2024 onward. Data for 2023 tags roughly half its Pillar II rows, and the rest read `NA`.

3. **Read the two warnings emitted by default-years sub-pillar queries.** When `years=None` (the default), a sub-pillar filter narrows automatically to 2023 onward, and a second warning notes the 2023 coverage gap.

   ```python
   ii_a = tossd.get_tossd(pillars=21, columns="minimal")
   ```

   ```text
   UserWarning: Sub-pillar filters are only meaningful from 2023 onward; narrowing the default years [2019, 2020, 2021, 2022, 2023, 2024] to [2023, 2024]. Pass years= explicitly to request years before 2023 (raises InvalidPillarError for a sub-pillar filter).
   UserWarning: 2023 sub-pillar tagging is incomplete: roughly 49% of 2023 pillar-2 rows carry no sub-pillar tag (the rollout wasn't yet complete that year). Treat 2023 sub-pillar splits as indicative, not reliable; 2024 onward is complete.
   ```

4. **Passing an explicit pre-2023 year with a sub-pillar filter raises an error.** Automatic narrowing applies only when `years=None`. Specifying an explicit year prior to 2023 alongside a sub-pillar filter raises an `InvalidPillarError`.

   ```python
   tossd.get_tossd(years=2021, pillars="II.A", columns="minimal")
   ```

   ```text
   InvalidPillarError: Sub-pillar filters (pillars=21/'II.A' or 22/'II.B') are not meaningful before 2023; requested year(s) [2021] predate that.
   ```

5. **Split Pillar II by sub-pillar across years with `df.tossd.subpillar_breakdown()`.** It takes the `tossd_pillar == 2` subset of whatever frame you pass internally, so query without a `pillars=` filter at all. Every year lands in the result, tagged and untagged alike, with no `dropna=False` groupby to remember.

   ```python
   p = tossd.get_tossd(years=[2023, 2024], columns="analysis", units="usd_million")
   p.tossd.subpillar_breakdown()
   ```

   ```text
      year subpillar  usd_disbursement  share_pct  coverage_pct
   0  2023      II.A      60465.333985  48.168490     66.553006
   1  2023      II.B      23077.865394  18.384516     66.553006
   2  2023  Untagged      41985.614871  33.446994     66.553006
   3  2024      II.A      66272.006313  54.441323     98.135964
   4  2024      II.B      53189.954160  43.694641     98.135964
   5  2024  Untagged       2269.110984   1.864036     98.135964
   ```

   `share_pct` is each row's share of its own year's Pillar II total. `coverage_pct` is that year's combined `II.A` + `II.B` share of the same total, repeated on all three of that year's rows since it describes the year, not the bucket. For 2023 that reads 66.6% value-share coverage. Step 2's `.notna()` recipe reads 50.6% row-share coverage for the same year. Both numbers are correct, and they answer different questions. Value-share coverage weighs a handful of large tagged activities more than row-share coverage does. State which one you're citing.

   <!-- prettier-ignore -->
   !!! warning "Heads up"
       A `0` in `II.A`/`II.B` before 2023 means the year predates sub-pillar tagging, not that Pillar II went unfunded. The whole total lands in `Untagged` instead.

       ```python
       p2021 = tossd.get_tossd(years=2021, columns="analysis", units="usd_million")
       p2021.tossd.subpillar_breakdown()
       ```

       ```text
          year subpillar  usd_disbursement  share_pct  coverage_pct
       0  2021      II.A          0.000000        0.0           0.0
       1  2021      II.B          0.000000        0.0           0.0
       2  2021  Untagged      85461.428145      100.0           0.0
       ```

       Trust an `II.A`/`II.B` split only where `coverage_pct` is non-trivial, from 2023 onward.

## Verify it worked

`subpillar_breakdown()`'s three subpillar rows partition every Pillar II row, so each year's `II.A` + `II.B` + `Untagged` amounts sum back to that year's own Pillar II total (aggregate rows excluded on both sides).

```python
breakdown = p.tossd.subpillar_breakdown()
year_totals = breakdown.groupby("year")["usd_disbursement"].sum()
pillar_2 = p.loc[~p["is_aggregate"] & (p["tossd_pillar"] == 2)]
year_totals.round(1).equals(pillar_2.groupby("year")["usd_disbursement"].sum().round(1))
```

```text
True
```

## Troubleshooting

**`InvalidPillarError` naming a year.** You passed `pillars=21`/`22` (or `"II.A"`/`"II.B"`) with an explicit `years=` argument containing years before 2023. Omit `years=` to use the 2023-onward default narrowing, or use `pillars=2` to query all Pillar II rows across any year without sub-pillar splits.

## See also

- [Pillars and aggregate rows](../about/pillars-and-aggregates.md) for the sub-pillar rollout context and reporting instructions.
- [Query reference](../reference/query.md) for `get_tossd`'s full `pillars=` filter options.
- [Verbs reference](../reference/verbs.md) for `subpillar_breakdown()`'s full parameter and return documentation.
