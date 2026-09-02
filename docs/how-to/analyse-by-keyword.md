# How to measure climate and gender finance with keyword markers

Tag a `get_tossd` frame with the twelve packaged keyword markers, then calculate disbursements per marker or combine multiple markers without double-counting activities tagged under several categories.

## Steps

1. **Query data using the `"analysis"` column preset.** Both `extract_keywords` and `keyword_totals` read `keywords_raw`, which is included in the `"analysis"` preset. The `"minimal"` preset omits it.

    ```python
    import tossd_reader as tossd

    df = tossd.get_tossd(years=2024, columns="analysis", units="usd_million")
    ```

2. **Extract marker columns for row-level analysis.** The `extract_keywords()` method adds a boolean `kw_<marker>` column for each marker, including `kw_gender`, `kw_adaptation`, and `kw_mitigation`. Filter rows with a boolean mask to analyse matching records directly, such as breaking down marker disbursements by recipient.

    ```python
    kw = df.tossd.extract_keywords()
    gender = kw[kw.kw_gender]
    gender.groupby("recipient_name", observed=True)["usd_disbursement"].sum().sort_values(
        ascending=False
    ).round(1).head(3)
    ```

    ```text
    recipient_name
    Developing countries, unspecified    9080.0
    India                                7420.9
    Indonesia                            3874.6
    Name: usd_disbursement, dtype: float64
    ```

3. **Aggregate disbursements per marker with `df.tossd.keyword_totals(markers=...)`.** This method aggregates disbursements per marker without double-counting activities tagged for multiple categories. It recomputes marker masks from `keywords_raw` internally and appends a `"Combined"` row containing the union of all requested marker masks.

    ```python
    df.tossd.keyword_totals(markers=["adaptation", "mitigation"])
    ```

    ```text
           marker  usd_disbursement  n_rows
    0  adaptation      38414.214244   41524
    1  mitigation      61608.343767   34279
    2    Combined      78643.461436   53822
    ```

    The individual marker rows sum to 100,022.6 million, exceeding `"Combined"`'s 78,643.5 million. An activity tagged for both adaptation and mitigation appears under each individual marker row, but only once in `"Combined"`, providing an unduplicated total for climate finance.

    The `n_rows` column counts matching rows rather than distinct activities. Reporting providers may split a single activity across multiple rows with different keyword tags. Omit `markers=` to compute totals across all twelve packaged markers and the `"Combined"` summary.

<!-- prettier-ignore -->
!!! warning "Marker overlaps and vocabulary scope"
    The twelve markers operate as independent boolean flags without weights or partitioning, so marker totals overlap by design. A row reading False across all `kw_` columns carries none of the packaged markers. In 2024, 10.9% of rows (51,436 of 474,026) contain `keywords_raw` tokens outside this twelve-marker vocabulary and remain False across every `kw_` column.

## Verify it worked

Sum the twelve marker counts and compare against the number of rows carrying at least one marker.

```python
kw_cols = [c for c in kw.columns if c.startswith("kw_")]
print(kw[kw_cols].sum().sum())
```

```text
258001
```

```python
print(kw[kw_cols].any(axis=1).sum())
```

```text
170206
```

The 258,001 marker instances span 170,206 rows. The difference represents rows carrying multiple markers, corresponding to the overlap accounted for by the `"Combined"` row in `keyword_totals()`.

## Troubleshooting

**`ValueError` naming `keywords_raw`.** Both `extract_keywords` and `keyword_totals` require `keywords_raw`. That column is included in the `"analysis"` and `"all"` presets. The `"minimal"` preset omits it.

```python
tossd.get_tossd(years=2024, columns="minimal").tossd.keyword_totals()
```

```text
ValueError: keyword_totals() needs column(s) keywords_raw, not present in df. Re-query with columns='analysis', or add keywords_raw to your columns= list.
```

**`ValueError` naming a `markers=` value.** `keyword_totals` rejects an unrecognised marker name and suggests the closest matches.

```python
df.tossd.keyword_totals(markers="adaptaion")
```

```text
ValueError: keyword_totals() marker 'adaptaion' not recognised; expected one of adaptation, biodiversity, covid_19, gender, idps_hostcommunities, mitigation, non_17_3_1, ppr_preparedness, ppr_response, refugees_hostcommunities, transnational_benefits_global, voluntaryrefugeereturn_reintegration. Closest matches: adaptation.
```

## See also

- [Helpers reference](../reference/helpers.md) for `extract_keywords` parameter details and the complete marker vocabulary.
- [Columns, presets, and units](../reference/columns.md) for columns included in `"analysis"`.
