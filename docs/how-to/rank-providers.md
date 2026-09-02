# How to rank providers by disbursement

Rank official providers by total disbursement with `df.tossd.rank_entities()`, which excludes aggregate summary rows by default so the ranking reflects individual reporting institutions.

## Steps

1. **Query data for the target year.** `rank_entities` needs `{dimension}_code`, `{dimension}_name`, and the value column it sums, all present in the `"analysis"` preset.

    ```python
    import tossd_reader as tossd

    df = tossd.get_tossd(years=2024, columns="analysis", units="usd_million")
    ```

2. **Inspect the effect of aggregate rows.** Published TOSSD files bundle summary rows (`provider_code == 0`, `provider_name == "Aggregate"`) alongside the providers that fund them. Pass `include_aggregates=True` to observe their impact.

    ```python
    cols = ["provider_code", "provider_name", "usd_disbursement", "share_pct", "rank"]
    print(
        df.tossd.rank_entities(top=3, include_aggregates=True)[cols].to_string(index=False)
    )
    ```

    ```text
     provider_code   provider_name  usd_disbursement  share_pct  rank
                 0       Aggregate      99379.609718  19.968737     1
               302   United States      67695.935324  13.602412     2
               918 EU Institutions      58667.476757  11.788288     3
    ```

    Aggregate rows outrank individual providers because they summarise total reporting. By default, `rank_entities` sets `include_aggregates=False` to exclude them from the ranking.

    ```python
    print(df.tossd.rank_entities(top=3)[cols].to_string(index=False))
    ```

    ```text
     provider_code   provider_name  usd_disbursement  share_pct  rank
               302   United States      67695.935324  16.996373     1
               918 EU Institutions      58667.476757  14.729604     2
                 4          France      25444.627005   6.388365     3
    ```

    `share_pct` shifts too. United States's share rises from 13.6% to 17.0% once Aggregate's USD 99.4 billion drops out of the total each share is measured against.

3. **Generate the complete ranking.** Drop the column subset to inspect every field `rank_entities` adds, including `n_activities`.

    ```python
    print(df.tossd.rank_entities(top=5).to_string(index=False))
    ```

    ```text
     provider_code                provider_name  usd_disbursement  n_activities  share_pct  rank
               302                United States      67695.935324         61832  16.996373     1
               918              EU Institutions      58667.476757         85406  14.729604     2
                 4                       France      25444.627005         14066   6.388365     3
               915 Asian Development Bank Group      18558.332668          4671   4.659428     4
               701                        Japan      17339.414452         17981   4.353395     5
    ```

    `n_activities` counts distinct `tossd_id` values per provider, excluding the `"0000"` placeholder that marks bundled lines with no activity identifier of their own.

<!-- prettier-ignore -->
!!! info "Disambiguation of shared entity names"
    `rank_entities` groups on the `(provider_code, provider_name)` pair. Some institutional families share a name across distinct reporting entities. The African Development Bank Group reports as both the African Development Bank (code 913) and the African Development Fund (code 914). Grouping on the pair keeps them apart.

<!-- prettier-ignore -->
!!! note "Activity counts and placeholder identifiers"
    `"0000"` also lands on a small share of individual providers' rows in 2023-24 (bundled lines belonging to reporting institutions), so `n_activities` can slightly undercount those providers even after aggregate rows are excluded.

<!-- prettier-ignore -->
!!! warning "Cross-pillar double-counting risk"
    `df` here carries both pillars. Ranking providers across both pillars mixes Pillar I bilateral outflows with Pillar II core contributions to multilateral institutions, which double-counts funding reported once by the donor and again by the institution it funds. See [Bilateral core contributions and multilateral double-counting](../about/pillars-and-aggregates.md#bilateral-core-contributions-and-multilateral-double-counting).

`rank_entities` works for any dimension with a matching `{dimension}_code`/`{dimension}_name` pair. Pass `dimension="recipient"` (or `"sector"`, `"purpose"`, `"channel"`) to rank a different one.

## Verify it worked

`share_pct` is each provider's share of the ranked total, so the full, untruncated ranking should sum to 100.

```python
print(df.tossd.rank_entities()["share_pct"].sum())
```

```text
100.0
```

## See also

- [Pillars and aggregate rows](../about/pillars-and-aggregates.md) for how aggregate rows are built and the bilateral/multilateral double-counting risk.
- [Columns, presets, and units](../reference/columns.md) for what the `"analysis"` preset includes.
