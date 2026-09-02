# How to filter by sector

Filter activity records to a specific sector by passing a name or code to `get_tossd(filters={"sector": ...})`. The published data's sector vocabulary operates at a higher level of aggregation than the packaged sector codelist, with sub-sector codes folded into top-level groups. This guide covers group-level filtering, vocabulary matching, and accessing sub-sector detail through purpose codes.

## Steps

1. **Filter by sector name or code.** The `filters=` parameter resolves sector values identically to `providers=` and `recipients=`, attempting an exact code match first before falling back to case-insensitive name matching against the packaged codelist.

    ```python
    import tossd_reader as tossd

    df = tossd.get_tossd(
        years=2024,
        columns="analysis",
        units="usd_million",
        filters={"sector": "I.2. Health"},
    )
    print(len(df))
    print(round(df["usd_disbursement"].sum(), 1))
    ```

    ```text
    53064
    30794.2
    ```

    <!-- prettier-ignore -->
    !!! note "Sector column visibility"
        The `columns="minimal"` preset applies filters correctly but omits `sector_code` and `sector_name` from the returned DataFrame. Use `"analysis"` or `"all"` (or specify columns explicitly) to retain the filtered columns in output tables.

2. **Verify sector granularity before filtering on sub-codes.** The published `sector_code` column contains 25 top-level groups (such as 110 Education, 120 Health, and 700 Humanitarian Assistance). The packaged codelist contains 50 entries, including sub-sector codes like 122 (`I.2.b. Basic health`) that reporting publishers fold into parent groups. Filtering directly on a folded sub-code returns an empty DataFrame with a warning.

    ```python
    sub_health = tossd.get_tossd(
        years=2024,
        columns="analysis",
        units="usd_million",
        filters={"sector": "I.2.b. Basic health"},
    )
    ```

    ```text
    UserWarning: get_tossd's filters matched no rows; returning an empty (but
    correctly typed) frame. A codelist entry can sit at a finer granularity
    than the published data uses (sector sub-codes, for example, fold into
    their top-level group) -- compare against the column's own values, e.g.
    df['sector_code'].unique().
    ```

    Group-level name filtering requires the codelist's exact prefixed format. The DataFrame `sector_name` column contains `"Health"`, whereas the codelist entry is prefixed as `"I.2. Health"`.

    ```python
    tossd.get_tossd(years=2024, filters={"sector": "Health"})
    ```

    ```text
    UnknownCodeError: 'Health' did not match any sector code or name in the
    packaged codelist. Closest matches: I.2. Health, I.2.a. Health, general,
    I.2.b. Basic health, I.3. Population policies/programmes and reproductive
    health.
    ```

3. **Access sub-sector detail using purpose codes.** Granular activity classifications are recorded in `purpose_code`, which contains 303 distinct values in 2024 data. Filter on `purpose` to query specific programme areas.

    ```python
    basic_health = tossd.get_tossd(
        years=2024,
        columns="analysis",
        units="usd_million",
        filters={"purpose": "Basic health care"},
    )
    print(len(basic_health))
    print(round(basic_health["usd_disbursement"].sum(), 1))
    ```

    ```text
    5536
    1883.1
    ```

    All matching rows retain `sector_code` 120 (Health). Purpose filtering refines the selection without altering the underlying sector code.

    ```python
    print(sorted(basic_health["sector_code"].unique().tolist()))
    ```

    ```text
    [120]
    ```

4. **Filter humanitarian assistance using the packaged name.** Sector 700 is a DAC group heading omitted from the OECD source codelist. The packaged sector codelist includes it as a supplemental entry, `VIII. Humanitarian Aid`, which `filters=` resolves like any standard sector.

    ```python
    hum = tossd.get_tossd(
        years=2024,
        columns="analysis",
        units="usd_million",
        filters={"sector": "VIII. Humanitarian Aid"},
    )
    print(len(hum))
    print(round(hum["usd_disbursement"].sum(), 1))
    ```

    ```text
    40668
    47179.8
    ```

    The name resolves to code 700 before filtering, making `filters={"sector": 700}` equivalent. The plain-English label `"Humanitarian Assistance"` present in `sector_name` does not resolve directly in `filters=`, which matches against the packaged codelist spelling.

    ```python
    tossd.get_tossd(years=2024, filters={"sector": "Humanitarian Assistance"})
    ```

    ```text
    UnknownCodeError: 'Humanitarian Assistance' did not match any sector code
    or name in the packaged codelist. Closest matches: VI.3. Other Commodity
    Assistance, VIII. Humanitarian Aid.
    ```

    Sector 700 contains sub-codes in the packaged codelist that fold into the parent group. Filtering on sub-code 720 (`VIII.1. Emergency Response`) returns an empty frame.

    ```python
    sub_emergency = tossd.get_tossd(years=2024, filters={"sector": 720})
    ```

    ```text
    UserWarning: get_tossd's filters matched no rows; returning an empty (but
    correctly typed) frame. A codelist entry can sit at a finer granularity
    than the published data uses (sector sub-codes, for example, fold into
    their top-level group) -- compare against the column's own values, e.g.
    df['sector_code'].unique().
    ```

    The `codes.browse("sector")` table includes an `in_published_data` column that identifies active codes directly.

    ```python
    sector = tossd.codes.browse("sector")
    print(sector[sector["code"].isin(["700", "720", "730", "740"])].to_string(index=False))
    ```

    ```text
    code                                      name  tossd_only                    source  in_published_data
     700                    VIII. Humanitarian Aid       False dac-sector-classification               True
     720                VIII.1. Emergency Response       False                  codelist              False
     730 VIII.2. Reconstruction and Rehabilitation       False                  codelist              False
     740             VIII.3. Disaster Preparedness       False                  codelist              False
    ```

    Code 700 is the aggregate group used in published data. Sub-codes 720, 730, and 740 fold into code 700 and do not appear in `sector_code` independently. See [How to look up codes and names](look-up-codes.md) for inspecting `in_published_data` across other dimensions.

5. **Rank sectors within a filtered dataset.** Use `df.tossd.rank_entities()` to sum, rank, and count activities per sector in a single call.

    ```python
    sen = tossd.get_tossd(
        years=2024, recipients="Senegal", columns="analysis", units="usd_million"
    )
    print(sen.tossd.rank_entities(dimension="sector", top=5).to_string(index=False))
    ```

    ```text
     sector_code                    sector_name  usd_disbursement  n_activities  share_pct  rank
              320 Industry, Mining, Construction        343.687506           104  15.697118     1
              230                         Energy        225.801199           127  10.312938     2
              210            Transport & Storage        213.414997           124   9.747228     3
              110                      Education        213.233284           528   9.738928     4
              310 Agriculture, Forestry, Fishing        175.566222           539   8.018574     5
    ```

    The `n_activities` column appears when the DataFrame contains `tossd_id`. See [How to rank providers by disbursement](rank-providers.md) for details on activity counting and aggregate-row exclusion.

6. **Count distinct activities across rows.** The `rank_entities` helper calculates `n_activities` automatically. When filtering `sector_code` manually, using `len()` alone overstates activity counts because activities spanning multiple sectors or purposes occupy multiple rows.

    ```python
    edu = sen[(sen["sector_code"] == 110) & ~sen["is_aggregate"]]
    print(len(edu))
    ```

    ```text
    553
    ```

    Count unique activities using distinct `tossd_id` values, excluding the `"0000"` placeholder used by publishers for bundled records lacking individual identifiers.

    ```python
    print(edu.loc[edu["tossd_id"] != "0000", "tossd_id"].nunique())
    ```

    ```text
    528
    ```

    The difference between row counts and activity counts varies by sector. In Senegal's 2024 data, education spans 553 rows across 528 distinct activities, whereas basic health care occupies 72 rows for 72 activities.

    ```python
    health = sen[(sen["purpose_code"] == 12220) & ~sen["is_aggregate"]]
    print(len(health), health.loc[health["tossd_id"] != "0000", "tossd_id"].nunique())
    ```

    ```text
    72 72
    ```

## Verify it worked

The `n_activities` count from `rank_entities` matches the manual distinct `tossd_id` calculation.

```python
ranked = sen.tossd.rank_entities(dimension="sector")
edu_activities = ranked.loc[ranked["sector_code"] == 110, "n_activities"].item()
print(edu_activities == edu.loc[edu["tossd_id"] != "0000", "tossd_id"].nunique())
```

```text
True
```

## Troubleshooting

- **`KeyError` on `sector_code` or `purpose_code`.** The DataFrame was queried with `columns="minimal"`. Re-query with `columns="analysis"` or `"all"`, or include the required column in an explicit `columns=` list.
- **A sector filter returns an empty frame with a `UserWarning`.** The requested codelist entry sits at a finer granularity than published data. Compare against `df["sector_code"].unique()`, or filter by `purpose` instead (step 3).

## See also

- [How to look up codes and names](look-up-codes.md) for browsing codelists and resolving tokens before filtering.
- [How to rank providers by disbursement](rank-providers.md) for `rank_entities` mechanics, `n_activities`, and aggregate-row handling.
- [Columns, presets, and units](../reference/columns.md) for full column specifications.
