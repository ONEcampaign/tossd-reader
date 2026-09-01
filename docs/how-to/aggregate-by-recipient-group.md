# How to aggregate disbursements by recipient country groups

Group recipient countries into standard classifications, Least Developed Countries, World Bank income tiers, or UN regions, with `df.tossd.add_recipient_group(scheme=...)`. It reads from a packaged, versioned table and keeps regional and multi-country flows in an explicit bucket instead of dropping them.

## Steps

1. **Add a recipient group with `add_recipient_group(scheme="ldc")`.**

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

   The three totals sum to USD 497.7 billion, the full published 2024 figure, because `df` here carries both pillars and the publisher's own aggregate rows. Most of `Regional / Multi-country Unallocated` (about USD 116 billion of the 147.4 billion) is Pillar II, whose activities are regional or global by design and were never going to resolve to one recipient country. The rest is genuinely regional Pillar I flows (codes like "Africa, regional" with no single-country ISO3) plus the aggregate rows' own share.

2. **Filter to Pillar I and drop aggregates first for a cross-border-only split.** If you want country-level foreign aid specifically, not Pillar II's global programmes, filter before grouping.

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

   `Regional / Multi-country Unallocated` is now 11.1% of the total, matching what a country-level ISO3 join would show, since Pillar II and the aggregate rows are both out of the picture.

3. **Switch schemes with `scheme="income"` or `scheme="region"`.**

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

   `Unclassified` (USD 350.8 million) is six non-self-governing territories the World Bank publishes no independent income data for: Saint Helena, Montserrat, the Cook Islands, Niue, Tokelau, and Wallis and Futuna. These are real, single-territory recipient codes, not aggregates, which distinguishes them from `Regional / Multi-country Unallocated`.

   `scheme="region"` never produces an `Unallocated` bucket. TOSSD publishes a real UN region for every recipient code, the regional ones included.

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

4. **Check for the São Tomé and Príncipe LDC divergence in 2024-vintage analysis.** São Tomé and Príncipe (`recipient_code` 268) graduated from LDC status on 2024-12-06. The packaged table reflects the current LDC list, so `scheme="ldc"` classifies its 2024 rows as `Other Developing Countries`, including the rows reported before the graduation date.

   ```python
   rg.loc[rg["recipient_code"] == 268, "recipient_group"].unique()
   ```

   ```text
   ['Other Developing Countries']
   Categories (3, str): ['Least Developed Countries', 'Other Developing Countries',
                         'Regional / Multi-country Unallocated']
   ```

   An analyst reconciling against a 2024-vintage LDC classification should treat STP as LDC for that year rather than trust this column as-is.

5. **Cite the classification vintage with `get_recipient_groups_version()`.**

   ```python
   tossd.get_recipient_groups_version()
   ```

   ```text
   'ldc-2024review/wb-fy27'
   ```

   The stamp names the UN LDC-list vintage and the World Bank income classification's fiscal year separately, since the two move on independent schedules. Record it alongside any published `recipient_group` figure.

## Verify it worked

Every recipient code resolves to a group, so the totals in step 1 sum back to `df`'s own grand total.

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

**`ValueError` naming a `scheme`.** You passed something other than `"ldc"`, `"income"`, or `"region"`.

```python
df.tossd.add_recipient_group(scheme="ld")
```

```text
ValueError: add_recipient_group() scheme='ld' is not one of 'income', 'ldc', 'region'.
```

**A `UserWarning` naming unmapped `recipient_code` values.** The packaged table doesn't cover a code your query returned, most likely because your TOSSD vintage is newer than the packaged snapshot. Those rows read `NA` in `recipient_group` rather than raising, so the rest of the frame stays usable.

## Next

- [Helpers reference](../reference/helpers.md) for `add_recipient_group()`'s full parameter and return documentation.
- [Rank providers by disbursement](rank-providers.md) for disaggregating flows by donor institution.
- [Join TOSSD to other country datasets](join-other-datasets.md) for merging World Bank or IMF metrics using ISO3 codes.
- [Pillars and aggregate rows](../about/pillars-and-aggregates.md) for what `is_aggregate` rows are and when to exclude them.
