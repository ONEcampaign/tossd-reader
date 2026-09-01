# Columns, presets, and units

The `tossd-reader` package processes 53 columns from each official TOSSD activity-level file, standardised into snake_case names and typed according to `schema.csv`. The `columns` parameter of `get_tossd` accepts a preset name (`"minimal"`, `"analysis"`, or `"all"`) or a list of specific snake_case column names. Four columns always appear in query results regardless of selection (`tossd_pillar`, `tossd_subpillar`, `is_aggregate`, and `unit`). The `is_aggregate` flag (`provider_code == 0`) and `unit` indicator are derived columns added by the package, bringing the `"all"` preset to 55 total columns.

## Presets

| Preset | Total Columns | Analytical Scope |
| --- | :---: | --- |
| `minimal` | 19 | Core identifiers, provider and recipient names, pillar categories, and financial amounts. |
| `analysis` | 44 | Adds sector classifications, channel codes, raw SDG tags, keyword fields, and financing modalities. |
| `all` | 55 | All packaged schema columns, derived fields, and any unmodelled publisher passthrough columns. |

## Memory footprint

| Preset (`columns=`) | Columns | 2024 (Single Year) | 2019 to 2024 (All Six Years) |
| --- | :---: | ---: | ---: |
| `"minimal"` | 19 | 55 MB | 278 MB |
| `"analysis"` | 44 | 102 MB | 505 MB |
| `"all"` (default) | 55 | 377 MB | 2.1 GB |

Memory figures represent pandas `memory_usage(deep=True)` across the official dataset.

## Schema columns

Columns are listed in source file order from `schema.csv`.

| Column | Dtype | Minimal | Analysis | Description |
| --- | --- | :---: | :---: | --- |
| `year` | `Int16` | Yes | Yes | Reporting year (2019 to 2024). |
| `provider_code` | `Int16` | Yes | Yes | Numeric provider code. Code `0` indicates an aggregate summary row. |
| `provider_name` | `category` | Yes | Yes | Standard English name of the provider country or multilateral institution. |
| `provider_agency_name` | `category` | | | Extending agency or department within the provider. |
| `tossd_id` | `string` | Yes | Yes | Unique TOSSD activity identifier. |
| `project_number` | `string` | Yes | Yes | Provider internal project or commitment identifier. |
| `recipient_code` | `Int16` | Yes | Yes | Numeric recipient country or regional code. |
| `recipient_name` | `category` | Yes | Yes | Standard English name of the recipient country, territory, or region. |
| `region_name` | `category` | | Yes | Geographic region of the recipient. |
| `channel_raw_text` | `string` | | | Unstructured channel text as reported by the provider. |
| `channel_code` | `Int32` | | Yes | Numeric code for the implementing channel organization. |
| `parent_channel_code` | `Int32` | | | Numeric code for the parent organization of the implementing channel. |
| `parent_channel_name` | `string` | | | Decoded English name of the parent channel organization from the channel codelist. |
| `other_partners` | `string` | | | Names of co-financing entities or implementing partners. |
| `channel_name` | `category` | | Yes | Standard category of the implementing channel. |
| `finance_instrument_code` | `Int16` | | Yes | Numeric code for the financial instrument (grants, debt, equity). |
| `finance_instrument_name` | `category` | | Yes | Name of the financial instrument. |
| `financing_arrangement_code` | `category` | | Yes | Code for the financing arrangement: blended finance, Islamic finance, recipient-counterpart co-financing, officially supported export credits, or SDR transactions. |
| `financing_arrangement_name` | `category` | | Yes | Name of the financing arrangement. |
| `framework_of_collaboration_code` | `category` | | Yes | Code for South-South or triangular collaboration frameworks. |
| `framework_of_collaboration_name` | `category` | | Yes | Name of the collaboration framework. |
| `modality_code` | `category` | | Yes | Code for the aid modality (e.g. project aid, core contributions). |
| `modality_name` | `category` | | Yes | Name of the aid modality. |
| `project_title` | `string` | | | Short title of the activity. |
| `external_link` | `string` | | | URL pointing to external project documentation. |
| `sdg_codes_raw` | `string` | | Yes | Semicolon-separated SDG goals and targets tagged for the activity. |
| `sdg_goal_level_explanation` | `string` | | | Narrative rationale for the assigned SDG classifications. |
| `keywords_raw` | `string` | | Yes | Pipe-separated thematic keywords (e.g. climate, biodiversity, gender). |
| `purpose_code` | `Int32` | | Yes | 5-digit DAC purpose code identifying the sector sub-discipline. |
| `purpose_name` | `category` | | Yes | Description of the 5-digit DAC purpose code. |
| `sector_name` | `category` | | Yes | Broad sector classification name (3-digit DAC sector). |
| `sector_code` | `Int16` | | Yes | 3-digit DAC sector code. |
| `isic_code` | `category` | | Yes | International Standard Industrial Classification (ISIC) industry code. |
| `isic_description` | `category` | | Yes | Description of the ISIC industry code. |
| `isic_section_letter` | `category` | | Yes | High-level ISIC section letter (e.g. A for Agriculture). |
| `isic_section_description` | `category` | | Yes | Description of the ISIC section. |
| `project_description` | `string` | | | Narrative description of project objectives and activities. |
| `tossd_pillar` | `Int8` | Yes | Yes | Pillar classification (`1` for Pillar I, `2` for Pillar II, `0` for legacy publisher placeholder rows). |
| `tossd_subpillar` | `category` | Yes | Yes | Sub-pillar category (`"21"` for Pillar II.A, `"22"` for Pillar II.B). |
| `usd_commitment`\* | `float64` | Yes | Yes | Total gross financial commitment in current USD thousands. |
| `usd_commitment_deflated`\* | `float64` | Yes | Yes | Total gross financial commitment in constant 2024 USD thousands. |
| `usd_disbursement`\* | `float64` | Yes | Yes | Gross financial disbursement in current USD thousands. |
| `usd_disbursement_deflated`\* | `float64` | Yes | Yes | Gross financial disbursement in constant 2024 USD thousands. |
| `usd_reflow`\* | `float64` | Yes | Yes | Financial reflows and repayments in current USD thousands. |
| `usd_reflow_deflated`\* | `float64` | Yes | Yes | Financial reflows and repayments in constant 2024 USD thousands. |
| `salary_cost` | `float64` | | | Administrative salary costs reported for technical cooperation. |
| `concessionality_flag` | `Int8` | | Yes | Concessionality status (`1` for concessional, `0` for non-concessional). |
| `maturity` | `Int16` | | Yes | Maturity duration for debt instruments as reported by the provider. |
| `mobilisation_instrument` | `category` | | Yes | Instrument used to mobilise private commercial finance. |
| `usd_amount_mobilised`\* | `float64` | Yes | Yes | Private capital mobilised by official interventions in current USD thousands. |
| `usd_amount_mobilised_deflated`\* | `float64` | Yes | Yes | Private capital mobilised in constant 2024 USD thousands. |
| `mobilisation_origin` | `string` | | | Geographic origin of mobilised private investment. |
| `source_name` | `category` | | Yes | Data source identifier for the reported activity. |

\* Reported in USD thousands. Specifying `units="usd_million"` divides these 8 columns by 1,000.

## Amount columns

| Column | 2024 Non-Null Rows | Analytical Scope |
| --- | ---: | --- |
| `usd_commitment` | 390,190 | Official commitments in current prices. |
| `usd_commitment_deflated` | 390,190 | Official commitments adjusted to 2024 constant prices. |
| `usd_disbursement` | 441,645 | Gross disbursements in current prices. |
| `usd_disbursement_deflated` | 441,645 | Gross disbursements adjusted to 2024 constant prices. |
| `usd_reflow` | 215,264 | Loan repayments and capital returns in current prices. |
| `usd_reflow_deflated` | 215,264 | Loan repayments adjusted to 2024 constant prices. |
| `usd_amount_mobilised` | 1,693 | Private finance mobilised in current prices. |
| `usd_amount_mobilised_deflated` | 1,693 | Private finance mobilised adjusted to 2024 constant prices. |

Each current price column has the identical non-null count as its corresponding deflated column. For conceptual differences between commitments, disbursements, reflows, and mobilised amounts, see [The amount columns](../about/amounts.md).

## Always present columns

These four columns appear in all query outputs:

| Column | Dtype | Analytical Role |
| --- | --- | --- |
| `tossd_pillar` | `Int8` | Pillar classification (`1` for Pillar I cross-border flows, `2` for Pillar II global public goods, `0` for publisher placeholder rows). |
| `tossd_subpillar` | `category` | Sub-pillar category (`"21"` for Pillar II.A, `"22"` for Pillar II.B), populated from 2023 onward. |
| `is_aggregate` | `bool` | True for summary records (`provider_code == 0`) and False for individual activity records. |
| `unit` | `category` | Denomination unit (`"usd_thousand"` or `"usd_million"`). |

## Data quality notes

- Empty strings in published files convert to typed null values in `get_tossd`. `get_tossd_raw` preserves raw publisher string representations.
- Modality code `c01` standardises to uppercase `C01`. Published files contain mixed case across different reporting years.
- The `maturity` column reflects values directly from the publisher without unit conversion.

## Schema drift detection

During data loading, `tossd_reader` compares published columns against `schema.csv`. A missing expected column, an unconvertible data type, or duplicate normalised column names raises `SchemaDriftError` identifying the affected column and offending value.

<!-- prettier-ignore -->
!!! warning "Heads up"

    Columns present in source files that do not appear in `schema.csv` emit a single warning per process and pass through under their original names when using `columns="all"`.

## Next

- [Pillars and aggregate rows](../about/pillars-and-aggregates.md). Pillar classification rules, aggregate row filtering, and structural breaks.
- [Query](query.md). Filter syntax and preset selection on `get_tossd`.
