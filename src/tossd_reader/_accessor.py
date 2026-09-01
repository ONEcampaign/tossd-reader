"""The `df.tossd` accessor: every verb and row helper as a `pandas.DataFrame` method.

`TossdAccessor` is registered as `df.tossd` via
`pd.api.extensions.register_dataframe_accessor`, called once in this
module's own body -- module bodies execute exactly once per process, so the
"import from both query.py and analysis.py, for the registration side
effect" wiring (see each module's own `# noqa: F401` import line) never
triggers pandas' re-registration `UserWarning`, no matter which of the two
modules a caller happens to import first, or whether both do.

Every delegate method below lazy-imports its target module (`verbs` or
`analysis`) inside the method body, never at module scope: `analysis.py`
imports this module (for the registration side effect), so a module-scope
import here of `analysis` (or `verbs`, which itself imports `analysis`)
would form an import cycle. `summary()` needs `query.FORCED_COLUMNS` for the
same reason -- `query.py` also imports this module for its side effect.

`TossdAccessor.__init__` does no validation of its own: every method below
raises the same teaching `ValueError`/`UnknownCodeError` its canonical
function (or `_require_columns`) already raises on the same input, so
duplicating a check here would only risk it drifting out of step with the
one that matters.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

import pandas as pd


@pd.api.extensions.register_dataframe_accessor("tossd")
class TossdAccessor:
    """`df.tossd` -- every `tossd_reader` aggregation verb and row helper, as methods.

    Delegate methods mirror their module-level function's own keyword
    arguments, minus `df`, and raise exactly what that function would on the
    same input: `rank_entities`, `compare_years`, `sdg_totals`,
    `keyword_totals`, `subpillar_breakdown` (from `tossd_reader.verbs`);
    `add_iso3`, `add_recipient_group`, `add_instrument_group`,
    `extract_keywords`, `explode_sdg`, `filter_provider_costs` (from
    `tossd_reader.analysis`).

    Accessor-only methods, with no module-level equivalent: `summary()`,
    `exclude_aggregates()`, `groupby_entity()` -- see each one's own
    docstring.
    """

    def __init__(self, pandas_obj: pd.DataFrame) -> None:
        """Store `pandas_obj`; no validation here -- each method's own teaching errors fire on use."""
        self._df = pandas_obj

    # --- accessor-only methods ------------------------------------------------

    def summary(self) -> pd.Series:
        """A printable one-row summary of the frame: years, sizes, pillar mix, unit.

        Returns:
            A `pandas.Series` indexed by field name: `"years"` (a sorted
            tuple of the distinct `year` values present, `()` if `df` is
            empty), `"n_rows"`, `"n_aggregate_rows"` (the `is_aggregate`
            sum), one `"n_pillar_{p}_rows"` entry per distinct
            `tossd_pillar` value present (ascending -- so a frame with only
            Pillar II rows carries no `n_pillar_1_rows` entry at all),
            `"unit"` (the frame's single `unit` value, or a sorted tuple of
            every distinct value present when there's more than one, `()`
            when there's none), and `"n_columns"`.

        Raises:
            ValueError: `df` is missing any of `FORCED_COLUMNS` -- the set
                `get_tossd()` output always carries, so a missing one means
                `df` isn't `get_tossd()`-shaped.
        """
        from tossd_reader.query import (  # noqa: PLC0415 - lazy: avoid a query<->_accessor cycle at module scope
            FORCED_COLUMNS,
        )

        df = self._df
        missing = [name for name in FORCED_COLUMNS if name not in df.columns]
        if missing:
            raise ValueError(
                f"df.tossd.summary() needs column(s) {', '.join(missing)} "
                "(FORCED_COLUMNS, always present in get_tossd() output) not "
                "present in df."
            )

        years = tuple(sorted(int(year) for year in df["year"].dropna().unique()))
        pillar_counts = df["tossd_pillar"].value_counts().sort_index()
        units_present = sorted(str(unit) for unit in df["unit"].dropna().unique())
        unit: object = (
            units_present[0] if len(units_present) == 1 else tuple(units_present)
        )

        fields: dict[str, object] = {
            "years": years,
            "n_rows": len(df),
            "n_aggregate_rows": int(df["is_aggregate"].sum()),
        }
        for pillar, count in pillar_counts.items():
            fields[f"n_pillar_{int(pillar)}_rows"] = int(count)
        fields["unit"] = unit
        fields["n_columns"] = len(df.columns)

        return pd.Series(fields)

    def exclude_aggregates(self) -> pd.DataFrame:
        """Drop `is_aggregate` rows.

        Returns:
            A new frame excluding every `is_aggregate` row, `df.attrs`
            copied onto it (A7).

        Raises:
            ValueError: `df` has no `is_aggregate` column.
        """
        from tossd_reader import (  # noqa: PLC0415 - lazy: avoid the _accessor<->analysis cycle
            verbs,
        )

        df = self._df
        result = verbs._exclude_aggregates(
            df, include_aggregates=False, func_name="df.tossd.exclude_aggregates"
        ).copy()
        result.attrs = dict(df.attrs)
        return result

    def groupby_entity(
        self, *, dimension: str = "provider"
    ) -> pd.api.typing.DataFrameGroupBy:
        """A `pandas` `GroupBy` over the `({dimension}_code, {dimension}_name)` pair.

        Args:
            dimension: The dimension to group by -- any prefix with a
                matching `{dimension}_code`/`{dimension}_name` column pair
                in `df`. `"provider"` (the default), `"recipient"`,
                `"sector"`, or any other packaged dimension pair.

        Returns:
            `df.groupby([f"{dimension}_code", f"{dimension}_name"],
            observed=True)` -- an unused category never appears as an empty
            group.

        Raises:
            ValueError: `df` is missing `{dimension}_code` or
                `{dimension}_name`.
        """
        from tossd_reader import (  # noqa: PLC0415 - lazy: avoid the _accessor<->analysis cycle
            analysis,
        )

        df = self._df
        code_column = f"{dimension}_code"
        name_column = f"{dimension}_name"
        analysis._require_columns(
            df, code_column, name_column, func_name="df.tossd.groupby_entity"
        )
        return df.groupby([code_column, name_column], observed=True)

    # --- tossd_reader.verbs delegates ------------------------------------------

    def rank_entities(
        self,
        *,
        dimension: str = "provider",
        value: str = "usd_disbursement",
        top: int | None = None,
        include_aggregates: bool = False,
    ) -> pd.DataFrame:
        """Delegates to `tossd_reader.rank_entities()`."""
        from tossd_reader import (  # noqa: PLC0415 - lazy: avoid the _accessor<->analysis cycle
            verbs,
        )

        return verbs.rank_entities(
            self._df,
            dimension=dimension,
            value=value,
            top=top,
            include_aggregates=include_aggregates,
        )

    def compare_years(
        self,
        *,
        value: str = "usd_disbursement_deflated",
        cohort: Literal["consistent", "all"] = "consistent",
        include_aggregates: bool = False,
    ) -> pd.DataFrame:
        """Delegates to `tossd_reader.compare_years()`."""
        from tossd_reader import (  # noqa: PLC0415 - lazy: avoid the _accessor<->analysis cycle
            verbs,
        )

        return verbs.compare_years(
            self._df,
            value=value,
            cohort=cohort,
            include_aggregates=include_aggregates,
        )

    def sdg_totals(
        self,
        *,
        value: str = "usd_disbursement",
        level: Literal["goal", "code"] = "goal",
        top: int | None = None,
        include_aggregates: bool = False,
    ) -> pd.DataFrame:
        """Delegates to `tossd_reader.sdg_totals()`."""
        from tossd_reader import (  # noqa: PLC0415 - lazy: avoid the _accessor<->analysis cycle
            verbs,
        )

        return verbs.sdg_totals(
            self._df,
            value=value,
            level=level,
            top=top,
            include_aggregates=include_aggregates,
        )

    def keyword_totals(
        self,
        *,
        markers: str | Iterable[str] | None = None,
        value: str = "usd_disbursement",
        include_aggregates: bool = False,
    ) -> pd.DataFrame:
        """Delegates to `tossd_reader.keyword_totals()`."""
        from tossd_reader import (  # noqa: PLC0415 - lazy: avoid the _accessor<->analysis cycle
            verbs,
        )

        return verbs.keyword_totals(
            self._df,
            markers=markers,
            value=value,
            include_aggregates=include_aggregates,
        )

    def subpillar_breakdown(
        self,
        *,
        value: str = "usd_disbursement",
        include_aggregates: bool = False,
    ) -> pd.DataFrame:
        """Delegates to `tossd_reader.subpillar_breakdown()`."""
        from tossd_reader import (  # noqa: PLC0415 - lazy: avoid the _accessor<->analysis cycle
            verbs,
        )

        return verbs.subpillar_breakdown(
            self._df, value=value, include_aggregates=include_aggregates
        )

    # --- tossd_reader.analysis delegates ---------------------------------------

    def add_iso3(self) -> pd.DataFrame:
        """Delegates to `tossd_reader.add_iso3()`."""
        from tossd_reader import (  # noqa: PLC0415 - lazy: avoid the _accessor<->analysis cycle
            analysis,
        )

        return analysis.add_iso3(self._df)

    def add_recipient_group(
        self, *, scheme: Literal["ldc", "income", "region"] = "ldc"
    ) -> pd.DataFrame:
        """Delegates to `tossd_reader.add_recipient_group()`."""
        from tossd_reader import (  # noqa: PLC0415 - lazy: avoid the _accessor<->analysis cycle
            analysis,
        )

        return analysis.add_recipient_group(self._df, scheme=scheme)

    def add_instrument_group(self) -> pd.DataFrame:
        """Delegates to `tossd_reader.add_instrument_group()`."""
        from tossd_reader import (  # noqa: PLC0415 - lazy: avoid the _accessor<->analysis cycle
            analysis,
        )

        return analysis.add_instrument_group(self._df)

    def extract_keywords(self) -> pd.DataFrame:
        """Delegates to `tossd_reader.extract_keywords()`."""
        from tossd_reader import (  # noqa: PLC0415 - lazy: avoid the _accessor<->analysis cycle
            analysis,
        )

        return analysis.extract_keywords(self._df)

    def explode_sdg(self, *, value: str | None = None) -> pd.DataFrame:
        """Delegates to `tossd_reader.explode_sdg()`."""
        from tossd_reader import (  # noqa: PLC0415 - lazy: avoid the _accessor<->analysis cycle
            analysis,
        )

        return analysis.explode_sdg(self._df, value=value)

    def filter_provider_costs(self) -> pd.DataFrame:
        """Delegates to `tossd_reader.filter_provider_costs()`."""
        from tossd_reader import (  # noqa: PLC0415 - lazy: avoid the _accessor<->analysis cycle
            analysis,
        )

        return analysis.filter_provider_costs(self._df)
