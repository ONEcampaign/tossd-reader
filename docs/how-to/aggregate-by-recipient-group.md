# How to aggregate disbursements by recipient country groups

Group recipient countries into standard classifications (Least Developed Countries, World Bank income tiers, or UN regions) with `df.tossd.add_recipient_group(scheme=...)`. The method reads from a packaged, versioned table and retains regional and multi-country flows in an explicit category.

## Steps

1. **Add recipient groups with `add_recipient_group(scheme="ldc")`.**

    ```python
    import tossd_reader as tossd

    df = tossd.get_tossd(years=2024, columns="analysis", units="usd_million")
    rg = df.tossd.add_recipient_group(scheme="ldc")
    rg.groupby("recipient_group", observed=True)["usd_disbursement"].sum().round(1)
    ```

    ```text
    recipient_group
    Least Developed Countries                88056.9
    Other Developing Countries              262225.0
    Regional / Multi-country Unallocated    147394.1
    Name: usd_disbursement, dtype: float64
    ```

    The three totals sum to USD 497.7 billion, matching the published 2024 total, because `df` includes both pillars and publisher-computed aggregate rows. Most of `Regional / Multi-country Unallocated` (USD 116.0 billion of the 147.4 billion) represents Pillar II expenditures, which are regional or global programmes that do not allocate to an individual recipient country. The remainder comprises regional Pillar I flows without a single-country ISO3 code and the aggregate rows' share.

2. **Filter to Pillar I to isolate cross-border flows.** To analyse country-level development finance, filter before grouping.

    ```python
    df1 = tossd.get_tossd(years=2024, pillars=1, columns="analysis", units="usd_million")
    df1 = df1[~df1["is_aggregate"]]
    rg1 = df1.tossd.add_recipient_group(scheme="ldc")
    rg1.groupby("recipient_group", observed=True)["usd_disbursement"].sum().round(1)
    ```

    ```text
    recipient_group
    Least Developed Countries                64164.4
    Other Developing Countries              181696.6
    Regional / Multi-country Unallocated     30704.2
    Name: usd_disbursement, dtype: float64
    ```

    `Regional / Multi-country Unallocated` accounts for 11.1% of the total, aligning with country-level ISO3 joins after excluding Pillar II and aggregate rows.

3. **Switch classification schemes with `scheme="income"` or `scheme="region"`.**

    ```python
    df.tossd.add_recipient_group(scheme="income").groupby("recipient_group", observed=True)[
        "usd_disbursement"
    ].sum().round(1)
    ```

    ```text
    recipient_group
    High income                               5629.8
    Low income                               60718.1
    Lower middle income                     119897.5
    Regional / Multi-country Unallocated    147394.1
    Unclassified                               350.8
    Upper middle income                     163685.6
    Name: usd_disbursement, dtype: float64
    ```

    `Unclassified` (USD 350.8 million) covers six non-self-governing territories for which the World Bank publishes no independent income classification: Saint Helena, Montserrat, the Cook Islands, Niue, Tokelau, and Wallis and Futuna. These are single-territory recipient codes distinct from `Regional / Multi-country Unallocated`.

    `scheme="region"` classifies all rows directly because TOSSD assigns a UN region to every recipient code, including regional groupings.

    ```python
    df.tossd.add_recipient_group(scheme="region").groupby("recipient_group", observed=True)[
        "usd_disbursement"
    ].sum().round(1).sort_values(ascending=False).head(5)
    ```

    ```text
    recipient_group
    South of Sahara                      94764.2
    Europe                               85502.9
    Developing countries, unspecified    85462.3
    South & Central Asia                 59971.0
    Global                                42160.4
    Name: usd_disbursement, dtype: float64
    ```

4. **Account for the São Tomé and Príncipe LDC graduation in 2024 analysis.** São Tomé and Príncipe (`recipient_code` 268) graduated from LDC status on 6 December 2024. The packaged table reflects the current LDC list, classifying all 2024 rows as `Other Developing Countries`.

    ```python
    rg.loc[rg["recipient_code"] == 268, "recipient_group"].unique()
    ```

    ```text
    ['Other Developing Countries']
    Categories (3, str): ['Least Developed Countries', 'Other Developing Countries',
                          'Regional / Multi-country Unallocated']
    ```

    When reconciling against a 2024-vintage LDC classification, treat São Tomé and Príncipe as an LDC for reporting periods prior to graduation.

5. **Cite the classification vintage with `get_recipient_groups_version()`.**

    ```python
    tossd.get_recipient_groups_version()
    ```

    ```text
    'ldc-2024review/wb-fy27'
    ```

    The identifier specifies the UN LDC-list vintage and the World Bank income classification fiscal year. Record this version tag alongside published figures.

## Verify it worked

Every recipient code resolves to a classification group, and the grouped totals sum back to the original dataset total.

```python
grand_total = round(df["usd_disbursement"].sum(), 1)
group_total = round(
    rg.groupby("recipient_group", observed=True)["usd_disbursement"].sum().sum(), 1
)
print(group_total == grand_total)
```

```text
True
```

## Troubleshooting

**`ValueError` naming a `scheme`.** Pass `"ldc"`, `"income"`, or `"region"`.

```python
df.tossd.add_recipient_group(scheme="ld")
```

```text
ValueError: add_recipient_group() scheme='ld' is not one of 'income', 'ldc', 'region'.
```

**`UserWarning` for unmapped `recipient_code` values.** If a query returns recipient codes newer than the packaged snapshot table, those rows receive `NA` in `recipient_group` while the rest of the dataset remains valid.

## See also

- [Helpers reference](../reference/helpers.md) for `add_recipient_group()` parameter specifications.
- [Rank providers by disbursement](rank-providers.md) for disaggregating flows by donor institution.
- [Join TOSSD to other country datasets](join-other-datasets.md) for merging external indicators using ISO3 codes.
- [Pillars and aggregate rows](../about/pillars-and-aggregates.md) for handling `is_aggregate` rows.
