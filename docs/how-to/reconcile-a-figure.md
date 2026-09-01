# How to check a figure against the published total

Reconcile a computed figure against the International Forum on TOSSD (IFT) data portal at [tossd.online](https://tossd.online) or an external spreadsheet by verifying six core data properties.

Load the multi-year dataset to evaluate reconciliation parameters.

```python
import tossd_reader as tossd

df = tossd.get_tossd(years=range(2019, 2025), columns="minimal")
```

## Checks

1. **Units.** The `get_tossd` function returns amounts in USD thousands by default (`units="usd_thousand"`). Inspect the `unit` column to verify the active scale.

   ```python
   df["unit"].unique()
   ```

   ```text
   ['usd_thousand']
   Categories (1, str): ['usd_thousand']
   ```

   Pass `units="usd_million"` to match figures published in millions.

2. **Aggregate rows.** The TOSSD dataset includes aggregate total rows (marked with `is_aggregate = True` and provider code `0`) alongside individual activity records.

   ```python
   int(df["is_aggregate"].sum())
   ```

   ```text
   38432
   ```

   Keep aggregate rows when reconciling the publisher's headline total. In 2024, they contribute USD 99.4 billion to the USD 497.7 billion total across all rows. Exclude them for provider rankings or other calculations restricted to named reporting institutions (`~df["is_aggregate"]`). See [How to rank providers by disbursement](rank-providers.md).

3. **Price basis (current versus constant).** Current prices (`usd_disbursement`) capture nominal flows, whereas deflated prices (`usd_disbursement_deflated`) express values in constant prices adjusted for inflation. Verify which price basis was used in the comparison figure. See [How to compare TOSSD totals across years](compare-years.md).

4. **Pillar filtering.** Filtering by `pillars=1` or `pillars=2` restricts records to Pillar I (cross-border flows) or Pillar II (global public goods). The default `pillars=None` includes all records, including unassigned pillar records from 2020 to 2023. Confirm whether the target figure applies a pillar filter.

5. **Data vintage and ETag.** The International Forum on TOSSD (IFT) updates annual data files in place at tossd.online. The `export` function records the file ETag and retrieval timestamp in the export manifest.

   ```python
   from pathlib import Path

   tossd.export("exports", years=2019)
   print(Path("exports/tossd_2019.manifest.json").read_text())
   ```

   ```text
   {
     "created_at": "2026-08-29T08:43:24.037603+00:00",
     "row_count": 290914,
     "schema_hash": "0a95f2c54852817a9db1a2174cffa5bd371d601e5d137a37cb27491182367df9",
     "tossd_reader_version": "0.1.0",
     "vintages": {
       "2019": {
         "etag": "\"69e6ac86-347a653\"",
         "retrieved_at": "2026-08-28T21:14:14.414671+00:00"
       }
     },
     "years": [
       2019
     ]
   }
   ```

   Matching `etag` values confirm identical data releases. Differing `etag` values indicate that the publisher updated the dataset between downloads.

6. **Year coverage.** Confirm that both calculations span the exact same set of reporting years.

   ```python
   int(df["year"].min()), int(df["year"].max()), df["year"].nunique()
   ```

   ```text
   (2019, 2024, 6)
   ```

   Figures produced before an annual release reflect a narrower year span.

## Verify it worked

Two figures agree once units, aggregate row filtering, price basis, pillar filters, vintage ETag, and year coverage all align.

## See also

- [About the amount columns](../about/amounts.md) for commitment versus disbursement definitions and price adjustments.
- [Reproducibility and vintages](../about/reproducibility.md) for tracking data revisions using HTTP ETags.
