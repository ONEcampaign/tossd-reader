# How to join TOSSD to other country datasets

Add ISO3 country codes to a `get_tossd` frame, then join it to World Bank, IMF, or in-house country data keyed on ISO3.

## Steps

1. **Add ISO3 codes.** `add_iso3` looks up `provider_code` and `recipient_code` against the standard OECD DAC codelist. Because provider names in published files vary or collide, use ISO3 codes when joining external datasets to distinguish sovereign countries from multilateral institutions and regional bodies.

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

   Aggregate rows (provider code `0`), multilateral organizations such as the African Development Bank Group, and non-sovereign TOSSD-only reporters resolve to `NA` for `provider_iso3`. Sovereign TOSSD-only providers, including Tunisia, Nigeria, Argentina, Brazil, and Indonesia, resolve to their own ISO3. A `how="left"` join keeps all activities and leaves `NA` in the joined columns. An `how="inner"` join silently drops activities from multilateral and aggregate providers.

## Verify it worked

Count the missing ISO3 values to identify rows that an inner join drops.

```python
print(iso["provider_iso3"].isna().sum())
```

```text
1864
```

In this Senegal query, 1,864 of 4,802 rows carry no `provider_iso3` because they represent multilateral providers or aggregate entries. Run the same verification on `recipient_iso3` when joining on recipient countries.

## Troubleshooting

**`ValueError` naming `provider_code` or `recipient_code`.** `add_iso3` requires at least one of these columns on the input frame. Both columns ship in all default presets. This error occurs when an explicit `columns=` list omits both columns.

## See also

- [Helpers reference](../reference/helpers.md) for `add_iso3` parameter definitions and lookup tables.
- [Pillars and aggregates](../about/pillars-and-aggregates.md) for details on aggregate rows.
