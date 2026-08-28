# Columns, presets, and units

_As of v0.1._

tossd_reader publishes 53 columns from each TOSSD activity-level file, renamed
to snake_case and cast to the dtypes in `schema.csv`. The `columns=` argument
to `get_tossd` selects a subset, a named preset (`"minimal"`, `"analysis"`,
or `"all"`, the default) or an explicit `list[str]` of snake_case names.
Four columns are forced into the result regardless of that selection:
`tossd_pillar`, `tossd_subpillar`, `is_aggregate`, and `unit`. `is_aggregate`
is derived as `provider_code == 0`. `parent_channel_name` is the one column
decoded from a codelist rather than read directly off the published file.

## Presets

| Preset     | Columns | Intent                                                                     |
| ---------- | :-----: | -------------------------------------------------------------------------- |
| `minimal`  |   19    | IDs, names, pillars, amounts.                                              |
| `analysis` |   44    | Adds sectors, channels, SDG and keyword raw fields, modalities.            |
| `all`      |   55    | Every packaged column, plus passthrough of any unexpected published extra. |

## Units

Amounts are published in USD thousands. `units="usd_million"` divides the 8
starred `usd_*` amount columns by 1000 (they're marked with `*` in the table
below) and sets `unit` to `"usd_million"` (`"usd_thousand"` otherwise).

## All columns

Generated from `schema.csv`, in publisher-file order.

| Column                            | Dtype      | Minimal | Analysis | Notes                 |
| --------------------------------- | ---------- | :-----: | :------: | --------------------- |
| `year`                            | `Int16`    |    ✓    |    ✓     |                       |
| `provider_code`                   | `Int16`    |    ✓    |    ✓     |                       |
| `provider_name`                   | `category` |    ✓    |    ✓     |                       |
| `provider_agency_name`            | `category` |         |          |                       |
| `tossd_id`                        | `string`   |    ✓    |    ✓     |                       |
| `project_number`                  | `string`   |    ✓    |    ✓     |                       |
| `recipient_code`                  | `Int16`    |    ✓    |    ✓     |                       |
| `recipient_name`                  | `category` |    ✓    |    ✓     |                       |
| `region_name`                     | `category` |         |    ✓     |                       |
| `channel_raw_text`                | `string`   |         |          |                       |
| `channel_code`                    | `Int32`    |         |    ✓     |                       |
| `parent_channel_code`             | `Int32`    |         |          |                       |
| `parent_channel_name`             | `string`   |         |          | decoded from codelist |
| `other_partners`                  | `string`   |         |          |                       |
| `channel_name`                    | `category` |         |    ✓     |                       |
| `finance_instrument_code`         | `Int16`    |         |    ✓     |                       |
| `finance_instrument_name`         | `category` |         |    ✓     |                       |
| `financing_arrangement_code`      | `category` |         |    ✓     |                       |
| `financing_arrangement_name`      | `category` |         |    ✓     |                       |
| `framework_of_collaboration_code` | `category` |         |    ✓     |                       |
| `framework_of_collaboration_name` | `category` |         |    ✓     |                       |
| `modality_code`                   | `category` |         |    ✓     |                       |
| `modality_name`                   | `category` |         |    ✓     |                       |
| `project_title`                   | `string`   |         |          |                       |
| `external_link`                   | `string`   |         |          |                       |
| `sdg_codes_raw`                   | `string`   |         |    ✓     |                       |
| `sdg_goal_level_explanation`      | `string`   |         |          |                       |
| `keywords_raw`                    | `string`   |         |    ✓     |                       |
| `purpose_code`                    | `Int32`    |         |    ✓     |                       |
| `purpose_name`                    | `category` |         |    ✓     |                       |
| `sector_name`                     | `category` |         |    ✓     |                       |
| `sector_code`                     | `Int16`    |         |    ✓     |                       |
| `isic_code`                       | `category` |         |    ✓     |                       |
| `isic_description`                | `category` |         |    ✓     |                       |
| `isic_section_letter`             | `category` |         |    ✓     |                       |
| `isic_section_description`        | `category` |         |    ✓     |                       |
| `project_description`             | `string`   |         |          |                       |
| `tossd_pillar`                    | `Int8`     |    ✓    |    ✓     |                       |
| `tossd_subpillar`                 | `category` |    ✓    |    ✓     |                       |
| `usd_commitment`\*                | `float64`  |    ✓    |    ✓     |                       |
| `usd_commitment_deflated`\*       | `float64`  |    ✓    |    ✓     |                       |
| `usd_disbursement`\*              | `float64`  |    ✓    |    ✓     |                       |
| `usd_disbursement_deflated`\*     | `float64`  |    ✓    |    ✓     |                       |
| `usd_reflow`\*                    | `float64`  |    ✓    |    ✓     |                       |
| `usd_reflow_deflated`\*           | `float64`  |    ✓    |    ✓     |                       |
| `salary_cost`                     | `float64`  |         |          |                       |
| `concessionality_flag`            | `Int8`     |         |    ✓     |                       |
| `maturity`                        | `Int16`    |         |    ✓     |                       |
| `mobilisation_instrument`         | `category` |         |    ✓     |                       |
| `usd_amount_mobilised`\*          | `float64`  |    ✓    |    ✓     |                       |
| `usd_amount_mobilised_deflated`\* | `float64`  |    ✓    |    ✓     |                       |
| `mobilisation_origin`             | `string`   |         |          |                       |
| `source_name`                     | `category` |         |    ✓     |                       |

\* Reported in USD thousands. `units="usd_million"` divides these 8 columns
by 1000.

## Always present

`tossd_pillar` and `tossd_subpillar` are `schema.csv` columns already carried
by every preset above. `is_aggregate` and `unit` are computed after the
schema read and aren't in `schema.csv` at all. All four are appended to the
result regardless of an explicit `columns=` list.

| Column            | Dtype      | Meaning                                                                                                                 |
| ----------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------- |
| `tossd_pillar`    | `Int8`     | Pillar number, `1`, `2`, or `0` for the 2020-2023 placeholder rows (a publisher artefact, unrelated to `is_aggregate`). |
| `tossd_subpillar` | `category` | Sub-pillar tag, `"21"` or `"22"`, where tagged.                                                                         |
| `is_aggregate`    | `bool`     | `provider_code == 0`.                                                                                                   |
| `unit`            | `category` | `"usd_thousand"` or `"usd_million"`, set by the `units=` argument to `get_tossd`.                                       |

## Schema drift

On every read, tossd_reader checks the published file's columns against
`schema.csv`. A published file missing a column the packaged schema expects
raises `SchemaDriftError`.

<!-- prettier-ignore -->
!!! warning "Heads up"

    A column the file carries that `schema.csv` doesn't recognize warns once
    per process and passes through under its original name, visible only
    under `columns="all"`.

## Next

- [Pillars, aggregates, and breaks](../about/data-model.md). Pillar and
  sub-pillar semantics, the pillar-0 placeholder rows, and the reporter-base
  structural break.
- [Query and export](query.md). `columns=` and `units=` in context, on
  `get_tossd` and `export`.
