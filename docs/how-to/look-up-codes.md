# How to look up provider and recipient codes

Look up official provider and recipient codes or names from the packaged codelists before querying `get_tossd`, and resolve unknown code errors.

## Steps

1. **List the available filter dimensions.**

   ```python
   import tossd_reader as tossd

   filters = tossd.get_available_filters()
   sorted(filters)
   ```

   ```text
   ['channel', 'finance_instrument', 'financing_arrangement', 'framework_of_collaboration', 'modality', 'pillar', 'provider', 'purpose', 'recipient', 'sector', 'years']
   ```

   The packaged codelists contain eleven dimensions. The `get_tossd` function accepts `providers`, `recipients`, and `pillars` as query arguments. Filter other dimensions such as sector, purpose, channel, and modality in pandas after querying, as shown in [How to filter by sector, purpose, channel, or modality](filter-by-sector.md).

2. **Inspect the target dimension DataFrame.**

   ```python
   filters["provider"].head(3)
   ```

   ```text
     code     name  tossd_only iso3
   0    1  Austria       False  AUT
   1    2  Belgium       False  BEL
   2    3  Denmark       False  DNK
   ```

3. **Pass the numeric code or exact name to `get_tossd`.** An unrecognized string raises `UnknownCodeError` with suggested matches.

   ```python
   tossd.get_tossd(years=2024, providers="Germny")
   ```

   ```text
   UnknownCodeError: 'Germny' did not match any providers code or name in the packaged codelist. Closest matches: Germany.
   ```

   Strings are validated against the packaged codelist. In-range integer codes pass directly to the query.

   ```python
   tossd.get_tossd(years=2024, providers=500, columns="minimal").shape
   ```

   ```text
   (0, 19)
   ```

   Provider code `500` matches the numeric column range, so the call returns an empty DataFrame with a warning when no records match.

   The provider codelist contains 159 rows while the recipient codelist contains 177 rows. Querying a recipient with a provider name raises an error.

   ```python
   tossd.get_tossd(years=2024, recipients="Japan")
   ```

   ```text
   UnknownCodeError: 'Japan' did not match any recipients code or name in the packaged codelist. Closest matches: Azerbaijan, Panama.
   ```

   Japan reports as an official provider in the TOSSD standard.

## Verify it worked

Check the row count to confirm that the resolved query returns matching records.

```python
df = tossd.get_tossd(years=2024, providers="Germany", columns="minimal")
df.shape[0] > 0
```

```text
True
```

## See also

- [Query reference](../reference/query.md) for code and name resolution rules behind `providers=`, `recipients=`, and `pillars=`.
- [How to rank providers by disbursement](rank-providers.md) for aggregating provider disbursements.
