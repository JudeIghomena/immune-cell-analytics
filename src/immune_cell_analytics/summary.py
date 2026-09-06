"""Relative-frequency summarization of immune cell populations.

Raw counts are not comparable across samples because each sample draws a
different total number of cells. Converting each population to its share of the
sample total (a relative frequency) is what makes samples comparable.
"""

from __future__ import annotations

import pandas as pd

from . import CELL_POPULATIONS

SUMMARY_COLUMNS: tuple[str, ...] = (
    "sample",
    "total_count",
    "population",
    "count",
    "percentage",
)


def relative_frequency_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return a long-format relative-frequency table, one row per population per sample.

    Parameters
    ----------
    df
        A cell-count frame containing a ``sample`` column and one column per
        population in :data:`CELL_POPULATIONS`.

    Returns
    -------
    pandas.DataFrame
        Columns ``sample``, ``total_count``, ``population``, ``count``,
        ``percentage`` where ``percentage`` is ``count / total_count * 100``.
        Samples whose populations sum to zero yield a percentage of 0.
    """
    populations = list(CELL_POPULATIONS)
    totals = df[populations].sum(axis=1)

    long = df[["sample", *populations]].melt(
        id_vars="sample",
        value_vars=populations,
        var_name="population",
        value_name="count",
    )

    total_by_sample = pd.Series(totals.to_numpy(), index=df["sample"].to_numpy())
    long["total_count"] = long["sample"].map(total_by_sample)

    # Guard against division by zero for empty samples.
    safe_total = long["total_count"].replace(0, pd.NA)
    long["percentage"] = (long["count"] / safe_total * 100).fillna(0.0).round(4)

    return long[list(SUMMARY_COLUMNS)].reset_index(drop=True)
