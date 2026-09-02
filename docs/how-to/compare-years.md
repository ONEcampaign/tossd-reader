# How to compare TOSSD totals across years

Compare multi-year TOSSD disbursements in constant prices with `df.tossd.compare_years()`, which holds the provider cohort constant across years by default and reports structural breaks intersecting the analysis window.

## Steps

1. **Query data across multiple years.**

    ```python
    import tossd_reader as tossd

    df = tossd.get_tossd(years=range(2019, 2025), columns="analysis", units="usd_million")
    ```

2. **Calculate year-over-year changes in constant prices.**

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

    The value column defaults to `usd_disbursement_deflated` (constant 2024 prices). The `n_providers` column remains constant at 91 across all rows, representing the `(provider_code, provider_name)` cohort present in every year under `cohort="consistent"`. The `pct_change` column shows the year-over-year percentage change for the deflated total. The initial year contains `NaN` as there is no prior year for comparison.

3. **Evaluate the effect of cohort filtering.** Pass `cohort="all"` to include every reporting provider in each year regardless of historical presence.

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

    The `n_providers` count increases from 97 in 2019 to 130 in 2024 under `cohort="all"`, whereas the default `cohort="consistent"` holds provider count steady at 91. Newly reporting providers add to the apparent growth rate under `cohort="all"`. The `cohort="consistent"` setting isolates underlying trends in financial volume.

4. **Inspect structural breaks across the time window.** The `compare_years()` method attaches matching entries from `get_structural_breaks(years=...)` to `result.attrs["structural_breaks"]`, scoped to the queried years.

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

    Four structural breaks intersect the 2019 to 2024 window: the 2022 initial appearance of sub-pillars, the 2023 sub-pillar rollout, the 2021 introduction of modality code K02, and expansion of the reporter base across the entire period. A shift aligning with one of these entries reflects a change in reporting practices rather than a fluctuation in financial transfers. See [Why TOSSD totals rise](../about/comparability.md) for details on each structural break.

## Verify it worked

Confirm that the provider cohort remains constant across all rows under default settings.

```python
print(result["n_providers"].nunique())
```

```text
1
```

## See also

- [Why TOSSD totals rise](../about/comparability.md) for the full structural-breaks table and drivers of multi-year trends.
- [About the amount columns](../about/amounts.md) for current versus constant prices and deflator base years.
