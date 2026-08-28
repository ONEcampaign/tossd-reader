# About pillars, aggregates, and breaks

_As of v0.1._

TOSSD's published files carry more structure than a flat activity table.
Rows belong to a pillar and, for recent years, a sub-pillar. Some rows are
publisher-computed aggregates rather than real providers. A handful of rows
in older files don't belong to any pillar at all. A year-over-year total can
also grow because the pool of reporting countries grew. `get_tossd()`
takes a position on each of these.

## The short answer

TOSSD splits activities into Pillar I (support to recipient countries) and
Pillar II (global and regional expenditures), with Pillar II further split
into II.A and II.B. Sub-pillar tagging exists only from 2023 and is only
reliable from 2024, so `get_tossd()` restricts sub-pillar filters to years
that can support them. Every published file also mixes real provider rows
with aggregate rows (`is_aggregate`) and, for 2020-2023, a batch of untagged
placeholder rows that `get_tossd()` drops the moment you filter by pillar.
Comparing totals across years needs one more check. The number of reporting
providers itself grew from 90 to 128 between 2019 and 2024.

## Pillars, sub-pillars, and the tagging rollout

Pillar I covers official support delivered to recipient countries. Pillar II
covers expenditures with no specific recipient, such as global public goods,
in-donor costs, and regional programmes. TOSSD splits Pillar II further into
II.A and II.B, recorded in `tossd_pillar`/`tossd_subpillar`.
`pillars=` accepts `1`/`"I"`, `2`/`"II"`, `21`/`"II.A"`, or `22`/`"II.B"`,
case-insensitively.

Sub-pillar tagging wasn't there from the start. 2022 carries 24 trace rows
out of roughly 128,900 pillar-2 rows that year, essentially a preview of the
tag rather than usable coverage. 2023 tags about 51% of pillar-2 rows,
leaving the rest unattributed to either sub-pillar. 2024 reaches about 99%.
A sub-pillar breakdown compared across years is only clean from 2024
onward. 2023 numbers move as more of that year's backlog gets tagged.

`get_tossd()` encodes this in the query itself. An explicit sub-pillar
filter combined with an explicit year before 2023 raises
`InvalidPillarError`:

```pycon
>>> tossd.get_tossd(years=2021, pillars="II.A")
Traceback (most recent call last):
    ...
InvalidPillarError: Sub-pillar filters (pillars=21/'II.A' or 22/'II.B') are
not meaningful before 2023; requested year(s) [2021] predate that.
```

With the default `years=None`, there's no explicit year to contradict, so
`get_tossd()` narrows silently to years >= 2023 and warns once instead of
raising. Requesting 2023 itself, narrowed or explicit, adds a second warning
naming the ~51% coverage figure, so a sub-pillar query touching 2023 always
says so.

!!! info "Why raise instead of narrow for an explicit year"

    A caller who wrote `years=2021` meant that year. Narrowing it away
    without saying so would return a result with a year silently missing,
    which is a worse failure than an error naming exactly why 2021 doesn't
    work with a sub-pillar filter. The default (`years=None`) has no such
    intent to contradict, so narrowing plus a warning is the right tradeoff
    there.

## Pillar-0 placeholder rows

The 2020 to 2023 files carry a few hundred rows tagged pillar `0`, a
publisher artefact rather than a third pillar. `pillars=None` (the default)
keeps them, so an unfiltered `get_tossd()` reproduces the row count of the
published file exactly. Passing any other `pillars=` value excludes them,
because `tossd_pillar in {1, 2}` never matches `0` and because a
pillar-filtered result shouldn't carry rows that no pillar claims.

## Aggregate rows and double counting

Every published file interleaves activity rows from real providers with
aggregate rows the publisher computes itself, tagged `provider_code == 0`
and displayed as "Aggregate". `get_tossd()` forces an `is_aggregate` column
into every result, regardless of `columns=`, so a caller can't accidentally
lose track of which rows are which.

!!! warning "Heads up"

    Aggregate rows carry a real share of the total, about 20% of 2024
    disbursements. Group by provider without excluding them and a provider
    ranking gains an extra "Aggregate" row sized like a major donor. Sum a
    total without excluding them and nothing changes, because the
    aggregate rows are already part of the publisher's headline figures.

```python
# ✅ Excludes aggregate rows before ranking real providers
provider_totals = (
    df.loc[~df["is_aggregate"]].groupby("provider_name")["usd_disbursement"].sum()
)

# ❌ Aggregate rows land in the ranking as if they were a provider
provider_totals = df.groupby("provider_name")["usd_disbursement"].sum()
```

Publisher-level totals (matching the headline Pillar I/II figures) want
`is_aggregate` rows included. Provider-level analysis wants them excluded.
`get_tossd()` can't know which one a given query is for, so it exposes the
column and leaves the choice to the caller.

## Units

Every amount column is published in USD thousands. `units="usd_million"`
divides the eight `usd_*` amount columns by 1000. `units="usd_thousand"`
(the default) leaves them as published. The `unit` column, forced into
every result alongside `is_aggregate`, names whichever of the two the rest
of the frame is currently in, so a frame passed between functions carries
its own units.

## Structural breaks and the growing reporter base

Part of the year-over-year growth in TOSSD totals is real activity, and
part of it is more providers reporting. The number of reporting providers
grew from 90 in 2019 to 128 in 2024. `get_structural_breaks()` returns a
five-row packaged reference table (`dimension`, `break_year`, `end_year`,
`description`, `source`) covering that reporter-base growth alongside the
sub-pillar rollout, a 2021 modality-code introduction, and a 2026 reporting
methodology change. The `reporters` row's `end_year` (2024) marks where its
drift ends, a caution against reading it as a year comparisons become safe.
The other four rows have `break_year` and `end_year` equal, one discrete
event each. The full table, with descriptions and sources, lives on
[Helpers reference](../reference/helpers.md).

## The Pillar II own-country-costs carve-out

Civil-society critiques of TOSSD Pillar II argue that a meaningful share of
it, administrative overhead and in-donor refugee costs, stays inside the
provider's own country rather than funding cross-border development.
`pillar2_own_country_costs()` isolates that share by filtering pillar-2 rows
to sector families 910 (administrative costs of donors) and 930 (domestic
expenditures for refugees and asylum seekers). On the 2024 data that's
35.6% of pillar-2 gross disbursements, consistent with the roughly 30%
share civil-society critiques attribute to these costs.

TOSSD publishes no official own-country-costs definition. This carve-out is
a verified heuristic built from the two sector families that match that
description. It is also approximate. Sector 930 is in-donor
spending by definition, but sector 910 is a proxy for donor administrative
overhead, most of which stays inside the provider's territory. A
`sector_code == 720` ("Humanitarian Assistance") candidate was considered
during verification and rejected, because those rows are ordinary
in-country humanitarian aid delivered by agencies like UNHCR and UNICEF.

## Alternatives we considered

**Drop the 2020-2023 pillar-0 rows everywhere, including the unfiltered
default.** This would have made every `get_tossd()` result pillar-clean,
but it would also break the one guarantee the unfiltered case is meant to
give, that `pillars=None` reproduces the published file's own row count.
Excluding pillar-0 rows only under an explicit `pillars=` filter keeps both
guarantees, fidelity when unfiltered and no unclaimed rows when filtered.

**Make `is_aggregate` optional, off by default.** A leaner default column
list is appealing, but the column exists specifically because forgetting
it produces a wrong answer that looks plausible (a provider ranking with
an extra outsized row). `is_aggregate` is one of four columns, with
`tossd_pillar`, `tossd_subpillar`, and `unit`, forced into every result.
The four-column cost stands regardless of this one. The alternative costs
a class of silent double-counting bugs we'd rather not ship.

## Consequences

Filtering by pillar or sub-pillar gives two guarantees. A result that
reproduces the publisher's own totals when unfiltered, and one that carries
no rows outside the pillar you asked for once you do filter. Grouping and
summing correctly does not depend on remembering that `provider_code ==
0` means something different from every other code. `is_aggregate` names
it directly, one of four columns (`tossd_pillar`, `tossd_subpillar`,
`is_aggregate`, and `unit`) that `columns=` can't project away.
Sub-pillar analysis of 2022 and 2023 requires acknowledging the coverage
gap up front, either by accepting the warning or by choosing `pillars=2`
(every pillar-2 row) rather than a sub-pillar filter.

## Limitations

2023 sub-pillar splits stay indicative rather than reliable, since roughly
half that year's pillar-2 rows carry no sub-pillar tag. Concessionality
(`concessionality_flag`) is a self-reported binary flag, so treat it as a
claim rather than a derived fact. TOSSD's own concessionality test differs
from ODA's grant-equivalent methodology too. TOSSD applies a flat
threshold, roughly a 35% grant element on a 5% discount rate, to loans and
equity only, while ODA's grant-equivalent system discounts cash flows
against reference rates that vary by recipient income group.

## When this might change

If TOSSD publishes an official own-country-costs definition,
`pillar2_own_country_costs()`'s sector-family heuristic would need to be
checked against it. The 2026 RDRM (revised debt-relief reporting
methodology) change on the structural-breaks table affects future vintages,
not the 2019-2024 files this page describes.

## Related

- [Query and export](../reference/query.md) for `get_tossd()`'s full
  parameter reference.
- [Helpers reference](../reference/helpers.md) for
  `get_structural_breaks()` and `pillar2_own_country_costs()`.
- [the tutorial](../tutorial.md) to see pillar and unit filtering in a
  worked example.
