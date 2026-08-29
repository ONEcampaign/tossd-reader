# How to check a figure against the published total

Work through six reasons a computed TOSSD figure can differ from the
publisher's portal, or from a colleague's spreadsheet, before assuming
either number is wrong.

Every check below runs against one six-year frame:

```python
import tossd_reader as tossd

df = tossd.get_tossd(years=range(2019, 2025), columns="minimal")
```

## Checks

1. **Units.** `get_tossd` returns USD thousands by default. Read the
   `unit` column:

   ```python
   df["unit"].unique()
   ```

   ```text
   ['usd_thousand']
   Categories (1, str): ['usd_thousand']
   ```

   Pass `units="usd_million"` to match a figure quoted in millions.

2. **Aggregate rows.** Provider code `0`, the publisher's own aggregate
   pseudo-provider, is in every result unless you drop it:

   ```python
   int(df["is_aggregate"].sum())
   ```

   ```text
   38432
   ```

   A provider or activity-count total that includes these rows won't match
   one that excludes them. See
   [How to rank providers by disbursement](rank-providers.md).

3. **Current versus deflated.** `usd_disbursement` and its twin,
   `usd_disbursement_deflated`, answer different questions. A multi-year
   comparison built on the current-price column carries inflation as well
   as new finance. See [How to compare TOSSD totals across
   years](compare-years.md).

4. **A `pillars=` filter.** Passing `pillars=1` or `pillars=2` excludes
   pillar-0 rows, a 2020-2023 publisher artefact with no pillar tag. The
   default `pillars=None` keeps them in. Check whether your query and the
   figure you're matching against made the same choice.

5. **Which vintage.** The publisher republishes each year in place, so two
   downloads of "2019" can still differ. `export()` writes the vintage's
   ETag and retrieval time into its manifest:

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

   Matching `etag` values mean the same vintage. A different `etag` means
   the publisher has revised that year since one of the two downloads.

6. **Year coverage.** Confirm both figures cover the same years:

   ```python
   int(df["year"].min()), int(df["year"].max()), df["year"].nunique()
   ```

   ```text
   (2019, 2024, 6)
   ```

   A colleague's spreadsheet built before a new year's file was published
   won't include it.

## Verify it worked

Two figures agree once units, aggregate rows, price basis, `pillars=`,
vintage, and year coverage all match. If a gap survives all six checks, the
difference is in how one of the figures was computed.

## See also

- [About the amount columns](../about/amounts.md) for the full
  commitments-versus-disbursements and current-versus-constant picture.
- [Reproducibility](../about/reproducibility.md) for how the ETag identifies
  a vintage.
