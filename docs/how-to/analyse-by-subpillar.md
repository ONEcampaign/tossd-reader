# How to split Pillar II into its sub-pillars

Filter to Pillar II.A or II.B with `pillars=`, check sub-pillar coverage
before you compare years, and get every pillar-2 row when tagging doesn't
matter for your question.

## Steps

1. **Filter with `pillars=`.** Pillar II.A takes `21`, `"21"`, or `"II.A"`;
   Pillar II.B takes `22`, `"22"`, or `"II.B"`. Matching is case-insensitive,
   so `"ii.a"` works too. All three forms of II.A return the same rows:

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

   Querying both sub-pillars for 2024 gives their disbursement split:

   ```python
   b = tossd.get_tossd(years=2024, pillars="II.B", columns="minimal", units="usd_million")
   print(round(a1["usd_disbursement"].sum(), 1), round(b["usd_disbursement"].sum(), 1))
   ```

   ```text
   76510.1 54782.7
   ```

2. **Check sub-pillar coverage before you compare years.** Sub-pillar
   tagging rolled out gradually. Measure it as the share of pillar-2 rows
   whose `tossd_subpillar` is `"21"` or `"22"`. An untagged pillar-2 row
   carries `tossd_subpillar == "2"`, the pillar value itself, so counting
   non-nulls would report full coverage in every year.

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
       A cross-year sub-pillar comparison is only clean from 2024. 2023
       tags about half its pillar-2 rows, and the untagged half sits under
       `tossd_subpillar == "2"`.

3. **Read the two warnings a default-years sub-pillar query emits.** With
   `years=None` (the default), a sub-pillar filter narrows silently to
   2023 onward, and a second warning names the 2023 coverage gap:

   ```python
   ii_a = tossd.get_tossd(pillars=21, columns="minimal")
   ```

   ```text
   UserWarning: Sub-pillar filters are only meaningful from 2023 onward; narrowing the default years [2019, 2020, 2021, 2022, 2023, 2024] to [2023, 2024]. Pass years= explicitly to request years before 2023 (raises InvalidPillarError for a sub-pillar filter).
   UserWarning: 2023 sub-pillar tagging is incomplete: roughly 49% of 2023 pillar-2 rows carry no sub-pillar tag (the rollout wasn't yet complete that year). Treat 2023 sub-pillar splits as indicative, not reliable; 2024 onward is complete.
   ```

4. **Name an explicit pre-2023 year with a sub-pillar filter and it raises
   instead of narrowing.** The silent narrowing applies only to the
   default `years=None`. An explicit year before 2023 combined with a
   sub-pillar filter is an error:

   ```python
   tossd.get_tossd(years=2021, pillars="II.A", columns="minimal")
   ```

   ```text
   InvalidPillarError: Sub-pillar filters (pillars=21/'II.A' or 22/'II.B') are not meaningful before 2023; requested year(s) [2021] predate that.
   ```

5. **Get every pillar-2 row regardless of tagging with `pillars=2`.** This
   is the only way to reach 2022's 24-row trace and every untagged 2023
   row alongside the tagged ones, with no year narrowing and no warning:

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

The three `tossd_subpillar` groups partition every pillar-2 row, so the
tagged and untagged counts add up to the frame's length:

```python
tagged = p2["tossd_subpillar"].isin(["21", "22"]).sum()
untagged = (p2["tossd_subpillar"] == "2").sum()
int(tagged + untagged) == len(p2)
```

```text
True
```

Pillar II's 2024 disbursements total 133561.8 USD million. Each group's
figure above is rounded on its own, so adding the three printed numbers
lands a decimal off that total.

## Troubleshooting

**`InvalidPillarError` naming a year.** You passed `pillars=21`/`22` (or
`"II.A"`/`"II.B"`) with an explicit `years=` that includes a year before
2023. Drop `years=` to fall back to the 2023-onward narrowing, or switch to
`pillars=2` for pre-2023 pillar-2 rows with no sub-pillar split.

## See also

- [Pillars and aggregate rows](../about/pillars-and-aggregates.md) for the
  sub-pillar rollout and why 2023 figures move as more of that year's
  backlog gets tagged.
- [Query reference](../reference/query.md) for `get_tossd`'s full `pillars=`
  contract.
