# How to check a figure against the published total

Reconcile a computed figure against the International Forum on TOSSD (IFT) data portal at [tossd.online](https://tossd.online) or an external spreadsheet. Run the same query you used to compute the figure, call `df.tossd.reconcile()` on the result, and read its entries against the figure you're checking. When one entry doesn't explain a mismatch, the checks below dig into that line.

## Run `reconcile()` first

```python
import tossd_reader as tossd

df = tossd.get_tossd(years=2024, columns="analysis", units="usd_million")

df.tossd.reconcile()
```

```text
unit                                 usd_million
n_aggregate_rows                            5626
aggregate_value                     99379.609718
aggregate_share_pct                    19.968737
usd_disbursement_total             497675.981441
usd_disbursement_deflated_total    497675.981441
pillars_present                           (1, 2)
year_min                                    2024
year_max                                    2024
n_years                                        1
has_provenance                              True
b02_core_contribution_value          6678.973842
b02_core_contribution_share_pct         1.342033
estimate_derived_value               2913.935663
estimate_derived_share_pct              0.585509
iso3_unmatched_value               147394.103994
iso3_unmatched_share_pct               29.616479
dtype: object
```

`reconcile()` provides a diagnostic summary of the DataFrame structure. It validates schema conformity rather than asserting data values. Every share is calculated against `df`'s own `usd_disbursement` total, aggregate rows included, so it accepts no `include_aggregates=` argument.

Read the entries against the figure you're checking:

- `unit`, `usd_disbursement_total`, and `usd_disbursement_deflated_total` cover units and price basis.
- `n_aggregate_rows`, `aggregate_value`, and `aggregate_share_pct` cover aggregate rows.
- `pillars_present`, `year_min`, `year_max`, and `n_years` cover pillar and year coverage.
- `has_provenance` confirms `df` carries a vintage record. Read it with `df.tossd.provenance()`.

Three entries extend beyond the checks below: `b02_core_contribution_*` sums core contributions to multilateral institutions (`modality_code == "B02"`), `estimate_derived_*` sums rows whose `source_name` designates them as an estimate (a heuristic derived from the source name), and `iso3_unmatched_*` sums rows `add_iso3` leaves unassigned to country codes (such as regional and multi-country codes or TOSSD-only entities). `usd_disbursement_deflated_total` equals `usd_disbursement_total` above because 2024 is the deflator base year. Other reporting years reflect deflator price adjustments. See [Verbs](../reference/verbs.md#reconcile-in-practice) for the full entry list, including a multi-year example.

## Checks

1. **Verify active units.** `reconcile()`'s `unit` field reports the active scale. `get_tossd` defaults to `usd_thousand`. Pass `units="usd_million"` to match figures published in millions.

2. **Check aggregate row inclusion.** `n_aggregate_rows`, `aggregate_value`, and `aggregate_share_pct` report summary rows. Above, aggregates contribute USD 99.4 billion of the USD 497.7 billion total across all rows. Keep aggregate rows when reconciling the publisher's headline total. Exclude them for provider rankings or calculations restricted to named reporting institutions (`~df["is_aggregate"]`, or `df.tossd.exclude_aggregates()`). See [How to rank providers by disbursement](rank-providers.md).

3. **Confirm the price basis.** Current prices (`usd_disbursement`) capture nominal flows. Deflated prices (`usd_disbursement_deflated`) hold constant prices adjusted for inflation. `usd_disbursement_total` and `usd_disbursement_deflated_total` present both bases side by side. Confirm which basis the external figure uses. See [How to compare TOSSD totals across years](compare-years.md).

4. **Verify pillar coverage.** `pillars_present` lists the distinct `tossd_pillar` values in `df`, showing `(1, 2)` above where all rows carry pillar assignments. Filtering by `pillars=1` or `pillars=2` on `get_tossd()` restricts rows to Pillar I (cross-border flows) or Pillar II (global public goods). The default `pillars=None` includes all pillars present. Confirm whether the figure you are checking applies a pillar filter.

5. **Compare data vintages and ETags.** `has_provenance` confirms `df` carries a vintage record, while [`df.tossd.provenance()`](../reference/verbs.md#get_provenance-in-practice) or an export manifest provides the ETag string. The IFT updates annual data files in place at tossd.online, and `export` records each file's ETag and retrieval timestamp in the manifest.

    ```python
    from pathlib import Path

    tossd.export("exports", years=2019)
    print(Path("exports/tossd_2019.manifest.json").read_text())
    ```

    ```text
    {
      "created_at": "2026-09-02T08:23:28.437587+00:00",
      "payload_sha256": "8a6eed10875a87fcd5faedece760bc461aa5926113ba1686613728c8c27d30bf",
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

    Matching `etag` values confirm identical data releases. A mismatched `etag` indicates the source file should be re-verified, because some server configurations alter ETags across requests without underlying content changes.

6. **Check the reporting year range.** `year_min`, `year_max`, and `n_years` report the temporal range. Confirm both figures span the same set of reporting years. A figure produced before an annual release reflects a narrower span than `reconcile()` shows for current data. On multi-year frames, `year_min`, `year_max`, and `n_years` span the entire query window.

## Verify it worked

Two figures agree once every `reconcile()` entry lines up: unit, price basis, aggregate share, pillar coverage, ETag, and year coverage.

## See also

- [About the amount columns](../about/amounts.md) for commitment versus disbursement definitions and price adjustments.
- [Reproducibility and vintages](../about/reproducibility.md) for tracking data revisions using HTTP ETags.
- [Verbs](../reference/verbs.md#reconcile-in-practice) for `reconcile()`'s full entry list and `get_provenance()`'s deep-copy and attrs-survival details.
