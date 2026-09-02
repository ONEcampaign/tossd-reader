# How to analyse financial instruments and concessionality

Evaluate debt vulnerabilities and financing terms by disaggregating flows across instrument categories (grants, concessional loans, non-concessional loans, and equity) and calculating net resource transfers after debt repayments.

## Steps

1. **Query activity records and classify instruments.** The `add_instrument_group()` method requires `finance_instrument_code` and `concessionality_flag`, both available in the `"analysis"` preset.

    ```python
    import tossd_reader as tossd

    df = tossd.get_tossd(years=2024, columns="analysis", units="usd_million")
    ig = df.tossd.add_instrument_group()
    ```

    The debt-instrument code family (`420`-`425`) splits into `"Concessional Loans"` and `"Non-concessional Loans"` by `concessionality_flag`: `1` indicates concessional terms and `0` indicates non-concessional terms. All other categories (`"Grants"`, `"Equity"`, `"Guarantees"`, `"Hybrid/Mezzanine"`, `"Direct Provider Spending"`, and `"Other Instruments"`) are mapped directly from `finance_instrument_code`.

2. **Aggregate disbursements by instrument group.** Retain unclassified rows by specifying `dropna=False`.

    ```python
    ig.groupby("instrument_group", dropna=False, observed=True)[
        "usd_disbursement"
    ].sum().round(1)
    ```

    ```text
    Concessional Loans           47194.6
    Direct Provider Spending     49378.8
    Equity                        2796.1
    Grants                      200931.0
    Guarantees                     882.3
    Hybrid/Mezzanine               467.2
    Non-concessional Loans       95923.0
    Other Instruments                8.7
    NaN                         100094.2
    ```

    The `NaN` bucket represents approximately 20% of 2024 disbursements. It combines pseudo-aggregate rows retained by `get_tossd()` by default (`provider_code == 0`, which lack individual `finance_instrument_code` values) and debt records with blank `concessionality_flag` fields that cannot be assigned to concessional or non-concessional groups. Standard pandas `groupby` operations drop `NaN` keys by default. Specify `dropna=False` or exclude aggregate rows before grouping.

3. **Exclude aggregate rows to isolate unclassified residuals.**

    ```python
    ex = df.tossd.exclude_aggregates()
    ig2 = ex.tossd.add_instrument_group()
    ig2.groupby("instrument_group", dropna=False, observed=True)[
        "usd_disbursement"
    ].sum().round(1)
    ```

    ```text
    Concessional Loans           47194.6
    Direct Provider Spending     49378.8
    Equity                        2796.1
    Grants                      200931.0
    Guarantees                     882.3
    Hybrid/Mezzanine               467.2
    Non-concessional Loans       95923.0
    Other Instruments                8.7
    NaN                            714.6
    ```

    Excluding aggregates removes the pseudo-aggregate component of `NaN`. The remaining USD 714.6 million (approximately 0.2% of the total) consists entirely of debt rows with blank `concessionality_flag` values. Setting `dropna=False` surfaces this residual in summary tables.

4. **Calculate net resource transfers after debt repayments.** Subtract `usd_reflow` (principal repayments and capital reflows returned to providers) from `usd_disbursement` to determine net financial transfers. Filter to Pillar I activities before calculating net resource flows.

    ```python
    p1 = tossd.get_tossd(years=2024, pillars=1, columns="analysis", units="usd_million")
    p1 = p1.tossd.exclude_aggregates().tossd.add_instrument_group()

    summary = (
        p1.groupby("instrument_group", dropna=False, observed=True)[
            ["usd_disbursement", "usd_reflow"]
        ]
        .sum()
        .reset_index()
    )
    summary["net_disbursement"] = summary["usd_disbursement"] - summary["usd_reflow"]
    summary["share_of_gross_pct"] = (
        summary["usd_disbursement"] / summary["usd_disbursement"].sum() * 100
    ).round(1)
    print(summary.round(1).to_string(index=False))
    ```

    ```text
            instrument_group  usd_disbursement  usd_reflow  net_disbursement  share_of_gross_pct
          Concessional Loans           47086.4     16356.6           30729.8                17.0
    Direct Provider Spending           13163.5       309.9           12853.7                 4.8
                      Equity            2790.5      1314.7            1475.8                 1.0
                      Grants          116268.9      1973.2          114295.7                42.0
                  Guarantees             882.2       859.3              22.9                 0.3
            Hybrid/Mezzanine             466.3       196.2             270.0                 0.2
      Non-concessional Loans           95190.0     52531.5           42658.5                34.4
           Other Instruments               2.9         0.0               2.9                 0.0
                         NaN             714.6       535.7             178.9                 0.3
    ```

    Published records include small reflow entries against grants (USD 2.0 billion of USD 116.3 billion in 2024, or under 2%). Verify grant net disbursements directly rather than assuming gross and net figures are identical.

    <!-- prettier-ignore -->
    !!! warning "Distinguishing mobilised private capital from official disbursements"
        Keep `usd_amount_mobilised` separate from `usd_disbursement`. The `usd_amount_mobilised` column measures private commercial capital mobilised through official interventions such as guarantees and syndicated loans, whereas `usd_disbursement` captures direct official fiscal transfers.

5. **Verify the classification vintage before publishing figures.**

    ```python
    tossd.get_instrument_groups_version()
    ```

    ```text
    'oecd-dac-cl15-2026-09-01/instrument-groups-methodology-v2'
    ```

    This stamp identifies the OECD DAC "List 15: Type of finance" source date alongside the project's methodology revision. A `finance_instrument_code` not present in the packaged table raises `UnknownCodeError` to prevent unrecognised codes from being grouped into `"Other Instruments"` unnoticed.

## Verify it worked

Confirm that the `dropna=False` aggregation matches the frame's total disbursement, and compare against a default `groupby` result.

```python
with_na = ig.groupby("instrument_group", dropna=False, observed=True)[
    "usd_disbursement"
].sum()
print(round(with_na.sum(), 1) == round(ig["usd_disbursement"].sum(), 1))
```

```text
True
```

```python
default = ig.groupby("instrument_group", observed=True)["usd_disbursement"].sum()
print(round(default.sum(), 1))
```

```text
397581.8
```

Default groupby behaviour drops the USD 100.1 billion `NaN` bucket entirely, producing USD 397,581.8 million instead of the full USD 497,676.0 million total.

## Troubleshooting

- **`ValueError` on `add_instrument_group()` naming missing columns.** The DataFrame was queried with `columns="minimal"` or a list missing `finance_instrument_code` or `concessionality_flag`. Re-query with `columns="analysis"`.

  ```python
  m = tossd.get_tossd(years=2024, columns="minimal", units="usd_million")
  m.tossd.add_instrument_group()
  ```

  ```text
  ValueError: add_instrument_group() needs column(s) finance_instrument_code, concessionality_flag, not present in df. Re-query with columns='analysis', or add finance_instrument_code, concessionality_flag to your columns= list.
  ```

- **`UnknownCodeError` on a `finance_instrument_code` value.** A TOSSD vintage newer than the packaged snapshot contains a code with no mapping. The helper raises an error to ensure new instruments are handled explicitly. Check `tossd.get_instrument_groups_version()` against the active data vintage, and refresh packaged codelists if necessary.

## See also

- [About the amount columns](../about/amounts.md) for `usd_disbursement`, `usd_reflow`, and financial metrics.
- [Pillars and aggregate rows](../about/pillars-and-aggregates.md) for the concessionality benchmark (35% grant element, 5% discount rate) implemented by `concessionality_flag`.
- [Helpers reference](../reference/helpers.md) for `add_instrument_group()` parameters and return contracts.
