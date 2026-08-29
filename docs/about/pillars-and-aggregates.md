# About pillars and aggregate rows

_As of v0.1._

TOSSD splits activities into Pillar I (support delivered to recipient
countries) and Pillar II (expenditure with no specific recipient, such as global
public goods, in-donor costs, and regional programmes). Pillar II further splits
into II.A and II.B, recorded in `tossd_pillar`/`tossd_subpillar`. Every
published file also mixes real provider rows with publisher-computed
aggregate rows, and a handful of older rows carry no pillar at all.

## Pillar I and Pillar II

`pillars=` filters to one of the two pillars, or to a specific sub-pillar,
case-insensitively. See [Query](../reference/query.md) for the exact
accepted values.

`sector` and `purpose_code` are single-valued per row in the published 2019
to 2024 files. A sum grouped by either column adds whole rows, with nothing to
split across categories first.

## The sub-pillar rollout

Sub-pillar tagging rolled out in stages. 2022 carries 24 trace rows out of
roughly 128,900 pillar-2 rows that year. 2023 tags about 51% of pillar-2
rows, leaving the rest unattributed to either sub-pillar. 2024 reaches about
99%. A sub-pillar breakdown compared across years is clean from 2024 onward.
2023 figures move as more of that year's backlog gets tagged.

`get_tossd()` encodes the rollout in the query itself. A sub-pillar filter
combined with an explicit year before 2023 raises `InvalidPillarError`,
naming the years that predate sub-pillar tagging. With the default
`years=None`, the same filter narrows silently to years 2023 onward, with one
warning. A sub-pillar filter that resolves to 2023 adds a second warning
naming the ~51% coverage figure. A query that needs every pillar-2 row,
tagged or not, can pass `pillars=2` instead of a sub-pillar filter.

## Aggregate rows

Every published file interleaves activity rows from real providers with
aggregate rows the publisher computes itself, tagged `provider_code == 0`
and displayed as "Aggregate". `get_tossd()` forces an `is_aggregate` column
into every result, regardless of `columns=`.

Aggregate rows carry about 20% of 2024 disbursements. Group by provider
without excluding them and a ranking gains an "Aggregate" row larger than
every real provider. A total that keeps them matches the publisher's headline
figure, and dropping them removes those aggregate disbursements.

```python
import tossd_reader as tossd

df = tossd.get_tossd(years=2024, columns="minimal", units="usd_million")

# ✅ Excludes aggregate rows before ranking providers
df.loc[~df["is_aggregate"]].groupby("provider_name")["usd_disbursement"].sum()

# ❌ Aggregate rows land in the ranking as if they were a provider
df.groupby("provider_name")["usd_disbursement"].sum()
```

Keep aggregate rows to match publisher-level headline figures. Exclude them when ranking individual providers. The full
recipe, with the 2024 figures, is on [How to rank providers by
disbursement](../how-to/rank-providers.md).

## Pillar-0 rows

The 2020 to 2023 files carry a few hundred rows tagged pillar `0`, a
publisher artefact from before the current two-pillar structure. `pillars=None`
(the default) keeps them, so an unfiltered `get_tossd()` reproduces the row
count of the published file exactly. Any other `pillars=` value excludes
them, because `tossd_pillar in {1, 2}` only matches pillars 1 and 2.

## Own-country costs

Part of Pillar II covers administrative overhead and in-donor refugee costs,
spending recorded inside the provider's own country.
`pillar2_own_country_costs()` isolates that share by filtering pillar-2 rows
to sector families 910 (administrative costs of donors, a proxy for donor
overhead) and 930 (domestic expenditures for refugees and asylum seekers). On
the 2024 data that's 35.6% of pillar-2 gross disbursements.

Sector 720 rows are in-country humanitarian aid delivered by agencies such as
UNHCR and UNICEF, so they fall outside the carve-out. TOSSD publishes no
official own-country-costs definition. The carve-out is the two sector
families that match that description.

## Concessionality

`concessionality_flag` is self-reported. TOSSD's concessionality test also
differs from ODA's grant-equivalent methodology. TOSSD applies a flat
threshold, roughly a 35% grant element on a 5% discount rate, to loans and
equity only. ODA's grant-equivalent system discounts cash flows against
reference rates that vary by recipient income group.

## Related

- [How to rank providers by disbursement](../how-to/rank-providers.md). The
  full aggregate-exclusion recipe, with the 2024 figures.
- [How to split Pillar II into its sub-pillars](../how-to/analyse-by-subpillar.md).
  The II.A/II.B filter, the 2023 coverage gap, and the warnings it raises.
- [Helpers](../reference/helpers.md). `pillar2_own_country_costs()`'s full
  parameter and return-value reference.
