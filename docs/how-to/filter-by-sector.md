# How to filter by sector, purpose, channel, or modality

Filter activity records by sector, purpose, channel, or modality codes using packaged codelists and pandas.

## Steps

1. **Look up the code from the relevant codelist.** The `get_available_filters` function returns eleven dimensions. The `get_tossd` function accepts `providers=`, `recipients=`, and `pillars=` directly. For sector, purpose, channel, and modality, look up the target code from the codelist and filter the returned DataFrame in pandas.

   ```python
   import tossd_reader as tossd

   sector = tossd.get_available_filters()["sector"]
   sector[sector["name"].str.contains("Education", case=False)]
   ```

   ```text
     code                                 name  tossd_only
   0  110                       I.1. Education       False
   1  111  I.1.a. Education, level nnspecified       False
   2  112               I.1.b. Basic education       False
   3  113     I.1.c. Upper secondary education       False
   4  114      I.1.d. Post-secondary education       False
   ```

2. **Query with a preset that includes the code column.** The `sector_code` column is included in `columns="analysis"` and `columns="all"`. The `columns="minimal"` preset excludes it.

   ```python
   sen = tossd.get_tossd(
       years=2024, recipients="Senegal", columns="analysis", units="usd_million"
   )
   sen.shape
   ```

   ```text
   (4802, 44)
   ```

3. **Filter the returned DataFrame on the code and separate aggregate rows.** The `sector_code` column is a nullable `Int16`. Use the `is_aggregate` flag to separate provider activities from aggregate totals.

   ```python
   edu = sen[(sen["sector_code"] == 110) & ~sen["is_aggregate"]]
   edu.sort_values("usd_disbursement", ascending=False)[
       ["provider_name", "sector_code", "sector_name", "usd_disbursement"]
   ].head(5)
   ```

   ```text
        provider_name  sector_code sector_name  usd_disbursement
   9           France          110   Education         64.863162
   507          Japan          110   Education         19.809865
   307        Türkiye          110   Education         13.456209
   144  United States          110   Education         11.702304
   445     Luxembourg          110   Education          8.716902
   ```

   ```python
   round(edu["usd_disbursement"].sum(), 1)
   ```

   ```text
   213.2
   ```

4. **Rank top sectors by total funding.** Group by sector code and name to identify the largest areas of development assistance across a country or portfolio.

   ```python
   top_sectors = (
       sen[~sen["is_aggregate"]]
       .groupby(["sector_code", "sector_name"], observed=True)["usd_disbursement"]
       .sum()
       .sort_values(ascending=False)
       .head(5)
       .reset_index()
   )
   top_sectors["share_pct"] = (
       top_sectors["usd_disbursement"]
       / sen[~sen["is_aggregate"]]["usd_disbursement"].sum()
       * 100
   ).round(1)
   top_sectors["usd_disbursement"] = top_sectors["usd_disbursement"].round(1)
   top_sectors
   ```

   ```text
      sector_code                         sector_name  usd_disbursement  share_pct
   0          230   Energy generation and supply                 532.1       20.1
   1          210   Transport & Storage                          468.4       17.7
   2          311   Agriculture                                  312.8       11.8
   3          110   Education                                    213.2        8.1
   4          140   Water Supply & Sanitation                    189.5        7.2
   ```

5. **Apply the same pattern to purpose, channel, and modality.** Look up the code and apply the same filtering pattern.

   ```python
   purpose_hits = tossd.get_available_filters()["purpose"]
   purpose_hits[purpose_hits["name"].str.contains("Basic health care", case=False)]
   ```

   ```text
         code                                       name  tossd_only
   22   12220                          Basic health care       False
   298  72011  Basic Health Care Services in Emergencies       False
   ```

   ```python
   channel_hits = tossd.get_available_filters()["channel"]
   channel_hits[channel_hits["name"].str.contains("Children", case=False)]
   ```

   ```text
         code                                      name  tossd_only
   79   21505                         Save the Children       False
   86   22502  Save the Children - donor country office       False
   139  41122           United Nations Children’s Fund         True
   ```

   Modality codes are category strings, such as `"B01"`. Filter and sum across purpose, channel, and modality using the same pattern.

   ```python
   purpose = sen[(sen["purpose_code"] == 12220) & ~sen["is_aggregate"]]
   channel = sen[(sen["channel_code"] == 41122) & ~sen["is_aggregate"]]
   modality = sen[(sen["modality_code"] == "B01") & ~sen["is_aggregate"]]

   print(len(purpose), round(purpose["usd_disbursement"].sum(), 1))
   print(len(channel), round(channel["usd_disbursement"].sum(), 1))
   print(len(modality), round(modality["usd_disbursement"].sum(), 1))
   ```

   ```text
   72 6.9
   383 19.4
   122 17.7
   ```

   The `sector_code`, `purpose_code`, `channel_code`, and `modality_code` columns, along with their paired `_name` columns, appear in `columns="analysis"`. Additional columns such as `channel_raw_text`, `parent_channel_code`, and `parent_channel_name` appear under `columns="all"`. Refer to [Columns, presets, and units](../reference/columns.md) for the complete column layout.

6. **Group by year with an explicit column selection.** `get_tossd` always includes `year`, along with `tossd_pillar`, `tossd_subpillar`, `is_aggregate`, and `unit`, in its output regardless of the `columns=` list.

   ```python
   df = tossd.get_tossd(
       years=range(2019, 2025),
       recipients="Senegal",
       columns=["sector_code", "sector_name", "usd_disbursement"],
       units="usd_million",
   )
   list(df.columns)
   ```

   ```text
   ['sector_code', 'sector_name', 'usd_disbursement', 'year', 'tossd_pillar', 'tossd_subpillar', 'is_aggregate', 'unit']
   ```

   ```python
   edu_by_year = df[(df["sector_code"] == 110) & ~df["is_aggregate"]]
   edu_by_year.groupby("year", observed=True)["usd_disbursement"].sum().round(1)
   ```

   ```text
   year
   2019    156.2
   2020    134.2
   2021    154.4
   2022    163.4
   2023    196.6
   2024    213.2
   Name: usd_disbursement, dtype: float64
   ```

## Verify it worked

Confirm that the 2024 multi-year sum matches the single-year filtered total.

```python
by_year = edu_by_year.groupby("year", observed=True)["usd_disbursement"].sum().round(1)
by_year[2024] == round(edu["usd_disbursement"].sum(), 1)
```

```text
True
```

## Troubleshooting

- **`KeyError` on a dimension code column** (`sector_code`, `purpose_code`, `channel_code`, `modality_code`). The DataFrame was queried with `columns="minimal"`. Re-query with `columns="analysis"` or `columns="all"`, or include the required column in an explicit `columns=` list.

## See also

- [How to look up provider and recipient codes](look-up-codes.md) for filterable dimensions and codelist lookups.
- [Columns, presets, and units](../reference/columns.md) for column definitions and preset details.
