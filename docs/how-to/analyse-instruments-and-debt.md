# How to analyse financial instruments and concessionality

Evaluating debt vulnerabilities and the terms of development finance requires disaggregating financial flows by instrument type (grants, concessional loans, non-concessional loans, and equity) and calculating net resource transfers after debt repayments.

This recipe shows how to categorize TOSSD financial instruments and calculate gross versus net disbursements.

## Recipe

```python
import pandas as pd
import tossd_reader as tossd

# 1. Query Pillar I activities with instrument and flow columns
df = tossd.get_tossd(
    years=2024,
    pillars=1,
    columns=[
        "provider_name",
        "finance_instrument_code",
        "finance_instrument_name",
        "concessionality_flag",
        "usd_disbursement",
        "usd_reflow",
    ],
    units="usd_million",
)
df = df[~df["is_aggregate"]]


# 2. Classify instruments into policy categories
def classify_instrument(row: pd.Series) -> str:
    code = row["finance_instrument_code"]
    if code in [110, 111, 112]:
        return "Grants"
    if code in [210, 211, 212]:
        if row["concessionality_flag"] == 1:
            return "Concessional Loans"
        return "Non-concessional Loans"
    if code in [410, 411, 412]:
        return "Equity"
    return "Other Instruments"


df["instrument_group"] = df.apply(classify_instrument, axis=1)

# 3. Calculate gross disbursements, repayments, and net transfers
summary = (
    df.groupby("instrument_group", observed=True)[["usd_disbursement", "usd_reflow"]]
    .sum()
    .reset_index()
)
summary["net_disbursement"] = summary["usd_disbursement"] - summary["usd_reflow"]
summary["share_of_gross_pct"] = (
    summary["usd_disbursement"] / summary["usd_disbursement"].sum() * 100
).round(1)
summary = summary.round(1)
summary
```

```text
         instrument_group  usd_disbursement  usd_reflow  net_disbursement  share_of_gross_pct
0      Concessional Loans           84712.3     34685.2           50027.1                23.3
1                  Equity            6952.1      1412.3            5539.8                 1.9
2                  Grants          142468.9         0.0          142468.9                39.1
3  Non-concessional Loans          127980.8     49890.1           78090.7                35.1
4       Other Instruments            2000.0         0.0            2000.0                 0.5
```

## Instrument definitions and net transfers

TOSSD records transactions across several instrument categories from the official codelist:

- **Grants (code 110 series):** Transfers made without repayment obligations. Reflows for grants are always zero.
- **Concessional Loans (code 210 series with `concessionality_flag == 1`):** Debt instruments meeting the TOSSD concessionality benchmark (at least 35% grant element calculated at a 5% discount rate).
- **Non-concessional Loans (code 210 series with `concessionality_flag == 0`):** Development lending extended at market or near-market terms.
- **Reflows (`usd_reflow`):** Principal repayments and capital reflows returned to the reporting provider during the reporting year. Subtracting `usd_reflow` from `usd_disbursement` calculates the net financial transfer received by developing countries.

<!-- prettier-ignore -->
!!! warning "Heads up"
    Do not add `usd_amount_mobilised` directly to `usd_disbursement`. The `usd_amount_mobilised` field measures private commercial capital mobilised through official interventions (such as guarantees and syndicated loans), whereas `usd_disbursement` captures direct official fiscal transfers.

## Next

- [About the amount columns](../about/amounts.md) for details on current prices, constant prices, and the eight financial metrics.
- [Rank providers by disbursement](rank-providers.md) for ranking donors by grant or loan volume.
