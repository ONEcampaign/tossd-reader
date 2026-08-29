# How to join TOSSD to other country datasets

Add ISO3 country codes to a `get_tossd` frame, then join it to World Bank, IMF, or in-house country data keyed on ISO3.

## Steps

1. **Add ISO3 codes.** `add_iso3` looks up `provider_code` and `recipient_code` against the OECD DAC codelist. Provider names collide in the published files. Use the ISO3 codes for joining to avoid merging distinct entities like the African Development Bank Group.

   ```python
   import tossd_reader as tossd

   sen = tossd.get_tossd(
       years=2024, recipients="Senegal", columns="minimal", units="usd_million"
   )
   iso = tossd.add_iso3(sen)
   iso[["provider_name", "provider_iso3", "recipient_name", "recipient_iso3"]].head()
   ```

   ```text
       provider_name provider_iso3 recipient_name recipient_iso3
   0           Italy           ITA        Senegal            SEN
   1          France           FRA        Senegal            SEN
   2         Belgium           BEL        Senegal            SEN
   3  United Kingdom           GBR        Senegal            SEN
   4   United States           USA        Senegal            SEN
   ```

2. **Join on the ISO3 column.**

   ```python
   import pandas as pd

   wdi = pd.read_csv("wdi_population.csv")  # keyed on iso3
   merged = iso.merge(wdi, left_on="provider_iso3", right_on="iso3", how="left")
   ```

Aggregates (provider code `0`), multilaterals such as the African Development Bank Group, and TOSSD-only entities all resolve to `NA` for `provider_iso3`. A `how="inner"` join drops those rows silently. `how="left"` keeps them, with `NA` in every joined column.

## Verify it worked

Count the nulls before joining to identify rows an inner join drops.

```python
iso["provider_iso3"].isna().sum()
```

```text
1864
```

1,864 of 4,802 rows carry no `provider_iso3`. The same check applies to `recipient_iso3` before joining on the recipient side.

## Troubleshooting

**`ValueError` naming `provider_code`/`recipient_code`.** `add_iso3` needs at least one of them present. Both ship in every column preset. This happens with an explicit `columns=` list that drops them.

## See also

- [Helpers reference](../reference/helpers.md) for `add_iso3`'s full contract.
- [Pillars and aggregates](../about/pillars-and-aggregates.md) for what aggregate and TOSSD-only rows are.
