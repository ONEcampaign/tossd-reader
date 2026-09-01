# How to compare TOSSD totals across years

Compare multi-year TOSSD disbursements in constant prices with `df.tossd.compare_years()`, which holds the provider cohort constant across years by default and reports any structural break intersecting the window.

## Steps

1. **Query the comparison years.**

   ```python
   import tossd_reader as tossd

   df = tossd.get_tossd(years=range(2019, 2025), columns="analysis", units="usd_million")
   ```

2. **Compare years.**

   ```python
   result = df.tossd.compare_years()
   print(result.to_string(index=False))
   ```

   ```text
    year  usd_disbursement_deflated  n_providers  pct_change
    2019              251882.812493           91         NaN
    2020              309200.621817           91   22.755745
    2021              312727.827661           91    1.140750
    2022              367005.467426           91   17.356191
    2023              374116.328363           91    1.937535
    2024              359866.711668           91   -3.808873
   ```

   The value column defaults to `usd_disbursement_deflated`, constant 2024 prices. `n_providers` holds at 91 across every row, the size of the `(provider_code, provider_name)` cohort present in all six years under the `cohort="consistent"` default. `pct_change` is the year-over-year percent change of that deflated total. The first year has no prior year to compare against, so it reads `NaN`.

3. **See what holding the cohort constant changes.** Pass `cohort="all"` to disable the restriction and count every reporting provider each year, whichever years it appears in.

   ```python
   result_all = df.tossd.compare_years(cohort="all")
   print(result_all.round(1).to_string(index=False))
   ```

   ```text
    year  usd_disbursement_deflated  n_providers  pct_change
    2019                   256779.3           97         NaN
    2020                   320616.2          109        24.9
    2021                   328418.1          119         2.4
    2022                   401734.8          129        22.3
    2023                   408381.8          129         1.7
    2024                   398296.4          130        -2.5
   ```

   `n_providers` climbs from 97 in 2019 to 130 in 2024 under `cohort="all"`. Under the default `cohort="consistent"` it stays flat at 91. New reporting providers inflate `cohort="all"`'s growth rate on top of any real change in spending. `cohort="consistent"` removes that effect from `pct_change`.

4. **Check the window for structural breaks.** `compare_years` copies `get_structural_breaks(years=...)`'s matching rows onto `result.attrs["structural_breaks"]`, already scoped to the years `df` covers.

   ```python
   breaks = result.attrs["structural_breaks"][["dimension", "break_year", "end_year"]]
   print(breaks.to_string(index=False))
   ```

   ```text
    dimension  break_year  end_year
   sub_pillar        2022      2022
   sub_pillar        2023      2023
     modality        2021      2021
    reporters        2019      2024
   ```

   Four breaks intersect 2019 to 2024: sub-pillar tagging's 2022 trace appearance, its 2023 rollout, modality code K02's 2021 introduction, and the reporter base's growth across the whole window. A jump that lines up with one of these rows reflects a reporting change, not a swing in real spending. See [Why TOSSD totals rise](../about/comparability.md) for what each row means.

## Verify it worked

Confirm the cohort held constant: under the default, `n_providers` should carry a single distinct value across all six rows.

```python
print(result["n_providers"].nunique())
```

```text
1
```

## See also

- [Why TOSSD totals rise](../about/comparability.md) for the full structural-breaks table and what drives multi-year growth.
- [About the amount columns](../about/amounts.md) for current versus constant prices and the deflator's 2024 base year.
