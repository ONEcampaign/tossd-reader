# How to look up provider and recipient codes

Resolve a provider or recipient name or code before passing it to
`get_tossd`, and read the error when a name doesn't match.

## Steps

1. **List the filterable dimensions.**

   ```python
   import tossd_reader as tossd

   filters = tossd.get_available_filters()
   sorted(filters)
   ```

   ```text
   ['channel', 'finance_instrument', 'financing_arrangement', 'framework_of_collaboration', 'modality', 'pillar', 'provider', 'purpose', 'recipient', 'sector', 'years']
   ```

   Eleven dimensions come back, but `get_tossd` only takes three as
   arguments: `providers`, `recipients`, and `pillars`. Filter sector,
   purpose, channel, and modality in pandas after the call, as [How to
   filter by sector, purpose, channel, or
   modality](filter-by-sector.md) shows.

2. **Inspect the dimension you need.**

   ```python
   filters["provider"].head(3)
   ```

   ```text
     code     name  tossd_only iso3
   0    1  Austria       False  AUT
   1    2  Belgium       False  BEL
   2    3  Denmark       False  DNK
   ```

3. **Pass the code or the exact name to `get_tossd`.** A misspelled name
   raises `UnknownCodeError` with suggestions:

   ```python
   tossd.get_tossd(years=2024, providers="Germny")
   ```

   ```text
   UnknownCodeError: 'Germny' did not match any providers code or name in the packaged codelist. Closest matches: Germany.
   ```

   A string is checked against the codelist. An in-range integer is not:

   ```python
   tossd.get_tossd(years=2024, providers=500, columns="minimal").shape
   ```

   ```text
   (0, 19)
   ```

   `500` fits the provider code column's range, so the call returns an
   empty frame and warns that the filters matched no rows.

   The provider codelist has 159 rows, the recipient codelist 177, so a
   name valid for one raises for the other:

   ```python
   tossd.get_tossd(years=2024, recipients="Japan")
   ```

   ```text
   UnknownCodeError: 'Japan' did not match any recipients code or name in the packaged codelist. Closest matches: Azerbaijan, Panama.
   ```

   Japan is a provider, not a TOSSD recipient.

## Verify it worked

An unvalidated integer code returns an empty frame, so check the row count:

```python
df = tossd.get_tossd(years=2024, providers="Germany", columns="minimal")
df.shape[0] > 0
```

```text
True
```

## See also

- [Query reference](../reference/query.md) for the full resolution rules
  behind `providers=`, `recipients=`, and `pillars=`.
- [How to rank providers by disbursement](rank-providers.md) for the next
  step once your provider or recipient list resolves.
