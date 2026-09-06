"""Relative-frequency table for immune cell populations.

The relative frequency of each population is defined once, in the SQL view
sample_population_frequency in load_data.py. This module reads that view and
surfaces it as a long-format table, one row per population per sample, with the
display precision the report expects.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

DEFAULT_DB = Path(__file__).resolve().parents[2] / "cell_count.db"

OUTPUT_COLUMNS: list[str] = ["sample", "total_count", "population", "count", "percentage"]

# Two decimals is the display precision for the report. The view stores full
# precision, so rounding happens here and nowhere upstream.
DISPLAY_DECIMALS = 2

_QUERY = """
SELECT sample_code AS sample, total_count, population, count, percentage
FROM sample_population_frequency
ORDER BY sample_code, population
"""


def relative_frequency_table(db_path: Path = DEFAULT_DB) -> pd.DataFrame:
    """Return the relative-frequency table read from the SQL view.

    The columns are sample, total_count, population, count, percentage, in that
    order, ordered by sample then population. Percentage is count / total_count
    * 100, rounded to two decimals for display. A zero-total sample has a NULL
    percentage from the view, which becomes NaN here rather than raising.

    Raises FileNotFoundError if db_path does not exist.
    """
    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found: {db_path}. Run 'python load_data.py' to build it."
        )

    with sqlite3.connect(db_path) as conn:
        table = pd.read_sql(_QUERY, conn)

    # A zero-total sample gives a NULL percentage, which pandas reads as an
    # object column holding None. Coerce to float so None becomes NaN and
    # rounding does not choke on it.
    percentage = pd.to_numeric(table["percentage"], errors="coerce")
    table["percentage"] = percentage.round(DISPLAY_DECIMALS)
    return table[OUTPUT_COLUMNS]


def write_relative_frequency_csv(
    out_path: Path,
    db_path: Path = DEFAULT_DB,
    table: pd.DataFrame | None = None,
) -> Path:
    """Write the relative-frequency table to out_path and return the path.

    Pass table to reuse a frame already in hand and avoid reading the view
    again. When table is None the frame is read from db_path. The parent
    directory is created if it does not already exist.
    """
    if table is None:
        table = relative_frequency_table(db_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_path, index=False)
    return out_path


def main() -> None:
    out_path = DEFAULT_DB.parent / "outputs" / "relative_frequencies.csv"
    table = relative_frequency_table()
    write_relative_frequency_csv(out_path, table=table)
    print(f"Wrote {len(table)} rows to {out_path}")
    print(table.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
