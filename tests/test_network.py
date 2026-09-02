"""Standing regression suite against the live TOSSD publisher.

Not part of the default test run: gated on `TOSSD_READER_NETWORK_TESTS=1` in
addition to pytest's own `network` marker (already deselected by default via
`-m "not network"` in `pyproject.toml`). Run manually or from a canary job:

    TOSSD_READER_NETWORK_TESTS=1 uv run pytest -m network

Tests download real publisher data (~30-90MB per test, via the normal
fetch/cache path) — that is expected, and each test is independent of the
others' execution order.
"""

from __future__ import annotations

import os
import warnings

import pyarrow.compute as pc
import pyarrow.parquet as pq
import pytest

from tossd_reader import _discovery, _schema, fetch, query

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        os.environ.get("TOSSD_READER_NETWORK_TESTS") != "1",
        reason="set TOSSD_READER_NETWORK_TESTS=1 to run the live publisher network suite",
    ),
]

_SMALLEST_YEAR = 2019
_EXPECTED_2019_ROW_COUNT = 290_914
"""2019's verified row count."""

_EXPECTED_2024_TOTALS_USD_K = {
    "p1_disb": 364_114_132.08,
    "p2_disb": 133_561_849.36,
    "mob": 79_646_259.46,
}
"""Gross disbursements by TossdPillar plus total USD_amountmobilised,
reproducing the publisher's own 2024 homepage prose (364.1bn / 133.6bn /
79.6bn) to 1dp."""
_TOLERANCE_USD_K = 1.0


def test_head_sweep_finds_known_years() -> None:
    """The HEAD sweep finds exactly the packaged known-years set, with ETags/sizes."""
    _discovery._reset_for_tests()
    vintages = _discovery.discover()

    assert set(vintages) == set(_discovery.known_years())
    for year, info in vintages.items():
        assert info.etag, f"{year}: missing ETag"
        assert info.size_bytes is not None and info.size_bytes > 0, (
            f"{year}: missing size_bytes"
        )


def test_smallest_year_conforms_to_packaged_schema() -> None:
    """apply_schema on a real downloaded vintage raises no drift and warns no extras.

    Any `SchemaDriftError`, or any unknown-extra-column warning (turned into a
    hard failure by the suite's global `filterwarnings = ["error"]`), fails
    this test.
    """
    path = fetch.fetch_year(_SMALLEST_YEAR)
    table = pq.read_table(path)

    result = _schema.apply_schema(table)

    assert result.num_rows == table.num_rows


def test_smallest_year_row_count_matches_recorded_value() -> None:
    """2019's row count matches the verified reference value."""
    path = fetch.fetch_year(_SMALLEST_YEAR)
    actual = pq.read_metadata(path).num_rows

    assert actual == _EXPECTED_2019_ROW_COUNT, (
        f"2019 row count changed: {actual} != {_EXPECTED_2019_ROW_COUNT} "
        "(vintage changed upstream? re-run the A1 audit)"
    )


@pytest.mark.slow
def test_2024_headline_reconciliation() -> None:
    """Gross disbursements by TossdPillar (+ total mobilised) reproduce the recorded 2024 reconciliation figures."""
    path = fetch.fetch_year(2024)
    table = pq.read_table(
        path, columns=["TossdPillar", "USD_disbursements", "USD_amountmobilised"]
    )

    pillar_1 = table.filter(pc.equal(table["TossdPillar"], "1"))
    pillar_2 = table.filter(pc.equal(table["TossdPillar"], "2"))
    actual = {
        "p1_disb": pc.sum(pillar_1["USD_disbursements"]).as_py(),
        "p2_disb": pc.sum(pillar_2["USD_disbursements"]).as_py(),
        "mob": pc.sum(table["USD_amountmobilised"]).as_py(),
    }

    for key, expected in _EXPECTED_2024_TOTALS_USD_K.items():
        assert actual[key] == pytest.approx(expected, abs=_TOLERANCE_USD_K), (
            f"2024 {key}: {actual[key]} vs expected {expected} "
            f"(tol {_TOLERANCE_USD_K} USD thousand)"
        )


@pytest.mark.slow
def test_2024_headline_reconciliation_full_pipeline() -> None:
    """`get_tossd(years=2024)` grouped sums reproduce the recorded 2024 reconciliation figures, end to end.

    Unlike `test_2024_headline_reconciliation` above (raw published columns,
    proving the source file itself), this drives the full schema/query
    pipeline: `is_aggregate` rows are not filtered out (no `providers=`/
    `pillars=` filter is applied), so a regression in the schema layer's
    typing or the query layer's derived columns/concat would show up here
    even if the raw-column check above still passed.
    """
    # The live vintage may carry a channel/decode code not yet in the packaged
    # codelist snapshot (that is a codelist-snapshot staleness signal for the
    # codelist-drift canary, not a reconciliation failure); this test only
    # cares about the numeric totals below, so any such warning is ignored
    # here rather than turned into a failure by the suite's global
    # filterwarnings=["error"].
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        df = query.get_tossd(years=2024)

    grouped = df.groupby("tossd_pillar")["usd_disbursement"].sum()
    actual = {
        "p1_disb": float(grouped.get(1, 0.0)),
        "p2_disb": float(grouped.get(2, 0.0)),
        "mob": float(df["usd_amount_mobilised"].sum()),
    }

    for key, expected in _EXPECTED_2024_TOTALS_USD_K.items():
        assert actual[key] == pytest.approx(expected, abs=_TOLERANCE_USD_K), (
            f"2024 {key}: {actual[key]} vs expected {expected} "
            f"(tol {_TOLERANCE_USD_K} USD thousand)"
        )


def test_e2e_get_tossd_raw_2019() -> None:
    """`get_tossd_raw(years=2019)` returns a non-empty frame with all 53 published columns."""
    df = fetch.get_tossd_raw(years=2019)

    assert not df.empty
    assert len(df.columns) == 53
