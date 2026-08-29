# How to filter by sector, purpose, channel, or modality

Look up a sector, purpose, channel, or modality code from its codelist, then filter a `get_tossd` frame on that code in pandas.

## Steps

1. **Look up the code from the relevant codelist.** `get_available_filters()` returns eleven dimensions, but `get_tossd` only takes `providers=`, `recipients=`, and `pillars=` as filter arguments. The packaged codelists for sector, purpose, channel, and modality exist so you can find a code to filter on in pandas after the query.

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

2. **Query with a preset that carries the code column.** `sector_code` ships with `columns="analysis"` and `columns="all"`. `columns="minimal"` omits it.

   ```python
   sen = tossd.get_tossd(
       years=2024, recipients="Senegal", columns="analysis", units="usd_million"
   )
   sen.shape
   ```

   ```text
   (4802, 44)
   ```

3. **Filter the returned frame on the code, with aggregate rows excluded.** `sector_code` is a nullable `Int16`, so a filter is a plain integer comparison.

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

4. **The same shape works for purpose, channel, and modality.** Look up the code, then filter on it the same way.

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

`modality_code` is a `category`, so its codes are short strings such as `"B01"`. Filter and total all three the same way `edu` was filtered above.

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

`sector_code`, `purpose_code`, `channel_code`, and `modality_code` (and their paired `_name` columns) all ship with `columns="analysis"`. `channel_raw_text`, `parent_channel_code`, and `parent_channel_name` appear only under `columns="all"`. Check [Columns, presets, and units](../reference/columns.md) for any column; a raw or parent column does not always follow its dimension's main code column.

5. **Name `"year"` yourself if you filter across years with an explicit `columns=` list.** Only `tossd_pillar`, `tossd_subpillar`, `is_aggregate`, and `unit` are forced into an explicit list. `"year"` is not, so grouping by it without naming it raises `KeyError`.

   ```python
   df = tossd.get_tossd(
       years=range(2019, 2025),
       recipients="Senegal",
       columns=["sector_code", "sector_name", "usd_disbursement"],
       units="usd_million",
   )
   df.groupby("year")["usd_disbursement"].sum()
   ```

   ```text
   KeyError: 'year'
   ```

Add `"year"` to the list and the same groupby works.

   ```python
   df = tossd.get_tossd(
       years=range(2019, 2025),
       recipients="Senegal",
       columns=["year", "sector_code", "sector_name", "usd_disbursement"],
       units="usd_million",
   )
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

The 2024 row of the multi-year, explicit-`columns=` total should match the single-year, `"analysis"`-preset total from step 3.

```python
by_year = edu_by_year.groupby("year", observed=True)["usd_disbursement"].sum().round(1)
by_year[2024] == round(edu["usd_disbursement"].sum(), 1)
```

```text
True
```

## Troubleshooting

**`KeyError` naming a dimension's code column** (`sector_code`, `purpose_code`, `channel_code`, `modality_code`). The frame was queried with `columns="minimal"`, which drops all four. Re-query with `columns="analysis"` or `columns="all"`, or add the column to an explicit `columns=` list.

**`KeyError: 'year'`** on a `groupby("year")`. An explicit `columns=` list does not force `"year"` in. Add `"year"` to the list.

## See also

- [How to look up provider and recipient codes](look-up-codes.md) for the full list of filterable dimensions and how code and name resolution work for `providers=` and `recipients=`.
- [Columns, presets, and units](../reference/columns.md) for the full column-to-preset table, and data quality notes like modality code normalization (e.g., `c01` to `C01`).
