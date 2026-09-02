# How to filter by sector

Filter activity records to one sector by passing a name or code straight to
`get_tossd(filters={"sector": ...})`. The published data's sector vocabulary
is coarser than the packaged sector codelist, so some codelist entries match
no rows at all. This guide covers group-level filtering, that mismatch, and
where the finer detail actually lives.

## Steps

1. **Filter by a sector name or code.** `filters=` resolves a sector value the
   same way `providers=` and `recipients=` resolve their own. It tries an
   exact code match first, then falls back to a case-folded name match
   against the packaged codelist.

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
   !!! note
       `columns="minimal"` filters correctly too, but drops `sector_code` and
       `sector_name` from the result. Use `"analysis"` or `"all"` (or list
       them explicitly) when you need to see the columns you filtered on, as
       every example on this page does.

2. **Know the sector vocabulary before you filter on a sub-code.** The
   published data's `sector_code` column holds 25 top-level groups: 110
   Education, 120 Health, 700 Humanitarian Assistance, and so on. The packaged
   sector codelist carries 50 entries, including sub-sector codes such as 122
   (`I.2.b. Basic health`) that the publisher folds into their group before
   publishing those files. Filter on one of those sub-codes and `get_tossd`
   returns an empty frame, correctly typed, with a warning:

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

   A group-level name has to match the codelist's own spelling too. The
   frame's `sector_name` column reads the plain `"Health"`. The codelist's own
   name is prefixed, `"I.2. Health"`.

   ```python
   tossd.get_tossd(years=2024, filters={"sector": "Health"})
   ```

   ```text
   UnknownCodeError: 'Health' did not match any sector code or name in the
   packaged codelist. Closest matches: I.2. Health, I.2.a. Health, general,
   I.2.b. Basic health, I.3. Population policies/programmes and reproductive
   health.
   ```

3. **Reach sub-sector detail through `purpose` instead.** The granularity a
   sector sub-code promises lives in the `purpose_code` column, which carries
   303 distinct values in the 2024 data. Filter `purpose` for the finer
   question.

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

   Every one of those rows still carries `sector_code` 120, the group Health.
   The detail `purpose` adds doesn't change the sector column.

   ```python
   print(sorted(basic_health["sector_code"].unique().tolist()))
   ```

   ```text
   [120]
   ```

4. **Filter humanitarian assistance by its packaged name.** Sector 700 is a
   DAC group heading the OECD source codelist doesn't carry. The packaged
   sector codelist adds it as a supplemental entry, `VIII. Humanitarian Aid`,
   and `filters=` resolves it the same way it resolves any other sector name.

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

   The name resolves to code 700 before the filter runs, so
   `filters={"sector": 700}` is the same filter spelled as a code.

   The plain-English label the publisher writes into the frame's own
   `sector_name` column, `"Humanitarian Assistance"`, still doesn't resolve.
   `filters=` matches names against the packaged codelist's own spelling.

   ```python
   tossd.get_tossd(years=2024, filters={"sector": "Humanitarian Assistance"})
   ```

   ```text
   UnknownCodeError: 'Humanitarian Assistance' did not match any sector code
   or name in the packaged codelist. Closest matches: VI.3. Other Commodity
   Assistance, VIII. Humanitarian Aid.
   ```

   The suggestion names the packaged entry that resolves.

   700 has sub-codes in the packaged codelist too, the same fold-into-group
   shape as the health sub-code in step 2. Filtering on one of them, 720
   (`VIII.1. Emergency Response`), returns nothing.

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

   `codes.browse("sector")` carries an `in_published_data` column that shows
   this directly, per code.

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

   700 is the group the publisher uses. 720, 730, and 740 fold into
   it and never appear in `sector_code` on their own. See
   [How to look up codes and names](look-up-codes.md) for reading
   `in_published_data` across the other dimensions.

5. **Rank sectors within a filtered frame.** `df.tossd.rank_entities()` sums,
   ranks, and counts activities per sector in one call, over any
   `get_tossd()` result.

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

   `n_activities` appears because `sen` carries `tossd_id`. See
   [How to rank providers by disbursement](rank-providers.md) for how
   `rank_entities` builds that count and why it excludes aggregate rows by
   default.

6. **Count activities, not rows.** `rank_entities` computes `n_activities`
   automatically. Filter `sector_code` by hand instead, and `len()` alone
   overstates how many activities were involved. The publisher publishes one
   row per activity-sector pairing, so an activity tagged with two sectors,
   or two purposes, shows up on two rows.

   ```python
   edu = sen[(sen["sector_code"] == 110) & ~sen["is_aggregate"]]
   print(len(edu))
   ```

   ```text
   553
   ```

   Count activities as distinct `tossd_id`, excluding the `"0000"` placeholder
   the publisher uses for bundled lines with no activity identifier of their
   own.

   ```python
   print(edu.loc[edu["tossd_id"] != "0000", "tossd_id"].nunique())
   ```

   ```text
   528
   ```

   The gap varies in size. Education narrows from 553 rows to 528 activities.
   The basic-health-care purpose filter from step 3, scoped to the same
   recipient, doesn't narrow at all.

   ```python
   health = sen[(sen["purpose_code"] == 12220) & ~sen["is_aggregate"]]
   print(len(health), health.loc[health["tossd_id"] != "0000", "tossd_id"].nunique())
   ```

   ```text
   72 72
   ```

## Verify it worked

`rank_entities`'s `n_activities` and the manual distinct-`tossd_id` count from
step 6 are the same computation reached two ways. They should agree.

```python
ranked = sen.tossd.rank_entities(dimension="sector")
edu_activities = ranked.loc[ranked["sector_code"] == 110, "n_activities"].item()
print(edu_activities == edu.loc[edu["tossd_id"] != "0000", "tossd_id"].nunique())
```

```text
True
```

## Troubleshooting

- **`KeyError` on `sector_code` or `purpose_code`.** The frame was queried
  with `columns="minimal"`. Re-query with `columns="analysis"` or `"all"`, or
  include the column in an explicit `columns=` list.
- **A sector filter returns an empty frame with a `UserWarning`.** The
  codelist entry sits at a finer granularity than the published data uses.
  Compare against `df["sector_code"].unique()`, or filter `purpose` instead
  (step 3).

## See also

- [How to look up codes and names](look-up-codes.md) for browsing a codelist
  and resolving a token before you filter on it.
- [How to rank providers by disbursement](rank-providers.md) for
  `rank_entities` mechanics, `n_activities`, and aggregate-row handling.
- [Columns, presets, and units](../reference/columns.md) for the full column
  layout.
