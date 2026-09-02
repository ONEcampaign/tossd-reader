# How to split Pillar II into its sub-pillars

Filter to Pillar II.A or II.B with `pillars=`, then split Pillar II by sub-pillar and year with `df.tossd.subpillar_breakdown()`. Review sub-pillar coverage when comparing years, distinguishing between row-share and value-share metrics.

## Steps

1. **Filter Pillar II activities with `pillars=`.** Pillar II.A accepts `21`, `"21"`, or `"II.A"`. Pillar II.B accepts `22`, `"22"`, or `"II.B"`. Matching is case-insensitive, so `"ii.a"` also works. All three forms of II.A return identical rows.

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

    Querying both sub-pillars for 2024 provides the disbursement breakdown between II.A and II.B.

    ```python
    b = tossd.get_tossd(years=2024, pillars="II.B", columns="minimal", units="usd_million")
    print(round(a1["usd_disbursement"].sum(), 1), round(b["usd_disbursement"].sum(), 1))
    ```

    ```text
    76510.1 54782.7
    ```

2. **Check sub-pillar coverage by row before comparing years.** Sub-pillar tagging rolled out gradually starting in 2023. The `tossd_subpillar` column is `NA` on any Pillar II row left untagged by the reporting provider, so `.notna()` calculates row-share coverage directly. The `df.tossd.subpillar_breakdown()` method (step 5) reports value-share coverage. Distinguish between these two metrics when citing coverage.

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
    !!! warning "Sub-pillar coverage gap in 2023"
        Cross-year sub-pillar comparisons are consistent from 2024 onward. Reporting for 2023 tags approximately half of all Pillar II rows, leaving the remainder as `NA`.

3. **Review warnings emitted by default-years sub-pillar queries.** When `years=None` (the default), a sub-pillar filter narrows automatically to 2023 onward, and a secondary warning notes the 2023 coverage gap.

    ```python
    ii_a = tossd.get_tossd(pillars=21, columns="minimal")
    ```

    ```text
    UserWarning: Sub-pillar filters are only meaningful from 2023 onward; narrowing the default years [2019, 2020, 2021, 2022, 2023, 2024] to [2023, 2024]. Pass years= explicitly to request years before 2023 (raises InvalidPillarError for a sub-pillar filter).
    UserWarning: 2023 sub-pillar tagging is incomplete: roughly 49% of 2023 pillar-2 rows carry no sub-pillar tag (the rollout wasn't yet complete that year). Treat 2023 sub-pillar splits as indicative, not reliable; 2024 onward is complete.
    ```

4. **Handle pre-2023 queries with sub-pillar filters.** Automatic narrowing applies only when `years=None`. Specifying an explicit year prior to 2023 alongside a sub-pillar filter raises an `InvalidPillarError`.

    ```python
    tossd.get_tossd(years=2021, pillars="II.A", columns="minimal")
    ```

    ```text
    InvalidPillarError: Sub-pillar filters (pillars=21/'II.A' or 22/'II.B') are not meaningful before 2023; requested year(s) [2021] predate that.
    ```

5. **Split Pillar II across years with `df.tossd.subpillar_breakdown()`.** This method isolates the `tossd_pillar == 2` subset internally, so query without a `pillars=` filter. Every year appears in the result across tagged and untagged categories.

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

    The `share_pct` column reports each row's share of its annual Pillar II total. The `coverage_pct` column reports the combined `II.A` + `II.B` share of the same total, repeated across all three rows for that year as an annual summary. For 2023, value-share coverage is 66.6%, whereas row-share coverage in step 2 is 50.6%. Value-share coverage places greater weight on large tagged activities. State which metric you are citing.

    <!-- prettier-ignore -->
    !!! warning "Interpreting pre-2023 zero values"
        A `0` in `II.A` or `II.B` for years prior to 2023 indicates that reporting predated sub-pillar tagging. The entire disbursement total is assigned to `Untagged`.

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

        Use `II.A`/`II.B` splits from 2023 onward where `coverage_pct` is substantial.

## Verify it worked

The three subpillar rows from `subpillar_breakdown()` partition every Pillar II row, so the sum of `II.A`, `II.B`, and `Untagged` disbursements reconstructs each year's Pillar II total (with aggregate rows excluded on both sides).

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

**`InvalidPillarError` naming a year.** You passed `pillars=21`/`22` (or `"II.A"`/`"II.B"`) with an explicit `years=` argument containing years before 2023. Omit `years=` to use the default 2023-onward window, or use `pillars=2` to query all Pillar II rows across any year without sub-pillar splits.

## See also

- [Pillars and aggregate rows](../about/pillars-and-aggregates.md) for sub-pillar rollout context and reporting instructions.
- [Query reference](../reference/query.md) for `get_tossd` filter options.
- [Verbs reference](../reference/verbs.md) for `subpillar_breakdown()` parameters and return structures.
