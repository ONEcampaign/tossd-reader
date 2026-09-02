# How to look up codes and names

Browse a packaged codelist or resolve one code or name to its packaged value with `tossd_reader.codes`, then pass the result straight to `get_tossd`.

## Steps

1. **Browse a dimension's codelist.** `tossd.codes.browse(dimension)` returns the packaged codelist frame for one of ten dimensions: `provider`, `recipient`, `pillar`, `sector`, `purpose`, `channel`, `modality`, `finance_instrument`, `financing_arrangement`, `framework_of_collaboration`.

   ```python
   import tossd_reader as tossd

   m = tossd.codes.browse("modality")
   print(m.head(4).to_string(index=False))
   ```

   ```text
   code                                                                     name  tossd_only  in_published_data
      A                                                           Budget support        True              False
    A00                                                           Budget support        True               True
      B                       Core contributions and pooled programmes and funds        True              False
    B01 Core support to NGOs, other private bodies, PPPs and research institutes        True               True
   ```

   Every codelist above carries an `in_published_data` bool except `pillar`, recording whether the code actually occurs in the published data across the packaged vintages. A codelist can carry entries the published data doesn't use. `modality`'s one-letter group codes, `A` and `B`, read `False` here, while the detail codes actually filed, `A00` and `B01`, read `True`. `sector` runs the other way. Its group code `700` (`VIII. Humanitarian Aid`) occurs in the data, while the sub-codes beneath it, `720`, `730`, and `740`, fold into the group and read `False`. `sector` alone also carries a `source` column, `codelist` for the OECD-fetched rows and `dac-sector-classification` for the one supplemental row.

   `get_available_filters()` returns all ten codelists at once, plus a synthetic `years` entry (eleven keys total), when you want everything in one dict instead of one dimension at a time.

2. **Resolve one code or name with `lookup()`.** `tossd.codes.lookup(dimension, token)` takes a code, a digit-string code, or a name (case-folded), and returns the resolved code. The return type follows the column: `provider`, `recipient`, `sector`, `purpose`, `channel`, and `finance_instrument` give back `int`; `modality`, `financing_arrangement`, and `framework_of_collaboration` give back `str`.

   ```python
   import tossd_reader as tossd

   print(tossd.codes.lookup("sector", "I.2.b. Basic health"))
   print(tossd.codes.lookup("provider", "France"))
   print(tossd.codes.lookup("modality", "B02"))
   ```

   ```text
   122
   4
   B02
   ```

3. **Trust `lookup()`'s result in a filter.** `codes.lookup()` resolves a token through the same matching path `filters=`, `providers=`, and `recipients=` use, so the code `lookup()` returns is exactly what a filter built from that same token would match. A resolvable code can still match zero rows in the published data (sector sub-codes, for example, fold into their top-level group before publishing). See [How to filter by sector](filter-by-sector.md) for the full story.

   <!-- prettier-ignore -->
   !!! warning "Heads up"
       A provider name doesn't always raise when looked up against the `recipient` dimension. 22 names, including Brazil, Argentina, and Indonesia, are both official providers and official recipients in the TOSSD standard. The lookup only fails for a provider-only name, like Japan.

       ```python
       import tossd_reader as tossd

       print(tossd.codes.lookup("recipient", "Brazil"))
       ```

       ```text
       431
       ```

4. **Ask for a dimension `lookup()` doesn't cover.** `browse()` accepts all ten packaged dimensions, `pillar` included. `lookup()` covers nine: every dimension `filters=` accepts, plus `provider` and `recipient`, each resolved through its own `providers=`/`recipients=` kwarg. `pillar` is the one exception. A pillar token like `"II.A"` doesn't resolve to a flat codelist code the way every other dimension does, so `lookup()` raises `ValueError` and points at `pillars=` instead.

   ```python
   import tossd_reader as tossd

   tossd.codes.lookup("pillar", "II.A")
   ```

   ```text
   ValueError: Unknown lookup() dimension 'pillar'; expected one of provider, recipient, sector, purpose, channel, modality, finance_instrument, financing_arrangement, framework_of_collaboration. Pillar tokens ('1', 'II.A', ...) resolve via get_tossd(pillars=...), not codes.lookup().
   ```

5. **Ask for a code or name that doesn't exist.** An unresolved token raises `UnknownCodeError`, naming the closest matches from the packaged codelist.

   ```python
   import tossd_reader as tossd

   tossd.codes.lookup("sector", "Helth")
   ```

   ```text
   UnknownCodeError: 'Helth' did not match any sector code or name in the packaged codelist. Closest matches: I.2. Health, I.2.a. Health, general, I.2.b. Basic health, I.3. Population policies/programmes and reproductive health.
   ```

## Verify it worked

Pass a `lookup()` result straight to `get_tossd` and confirm it resolves to matching rows.

```python
import tossd_reader as tossd

code = tossd.codes.lookup("provider", "France")
df = tossd.get_tossd(years=2024, providers=code, columns="minimal")
print(df.shape[0] > 0)
```

```text
True
```

## Troubleshooting

- **`UnknownCodeError` on a token you expected to resolve.** Check the exact packaged spelling with `browse(dimension)` first; the suggestions in the error list the closest packaged names, not necessarily the one you meant.
- **A filter built from a `lookup()` result matches zero rows.** The code resolved, but the published data doesn't carry that granularity. See [How to filter by sector](filter-by-sector.md).
- **`ValueError: Unknown lookup() dimension 'pillar'`.** Pillar tokens don't go through `codes.lookup()`. Pass the token to `get_tossd(pillars=...)` directly. See [About pillars and aggregate rows](../about/pillars-and-aggregates.md).

## See also

- [Query reference](../reference/query.md) for the full resolution rules behind `providers=`, `recipients=`, and `filters=`.
- [How to filter by sector](filter-by-sector.md) for applying a resolved code as a filter and the sub-sector granularity story.
