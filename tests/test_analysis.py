"""Tests for the relative-frequency table.

The table is built from a temp database loaded by load_data.build_database, so
the real root database is never touched. The per-sample percentage sum test
tolerates rounding: the view carries full precision, but the table rounds each
percentage to two decimals for display, so the sum is close to but not exactly
100.
"""

import sqlite3
from pathlib import Path

import load_data
import pandas as pd
import pytest

from immune_cell_analytics.analysis import (
    OUTPUT_COLUMNS,
    relative_frequency_table,
    write_relative_frequency_csv,
)

CSV = load_data.find_csv()


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    load_data.build_database(CSV, path)
    return path


def test_row_count(db: Path) -> None:
    table = relative_frequency_table(db)
    assert len(table) == 52500  # 10500 samples * 5 populations


def test_columns_exact_order(db: Path) -> None:
    table = relative_frequency_table(db)
    assert list(table.columns) == ["sample", "total_count", "population", "count", "percentage"]
    assert list(table.columns) == OUTPUT_COLUMNS


def test_known_sample_values(db: Path) -> None:
    table = relative_frequency_table(db)
    row = table[(table["sample"] == "sample00000") & (table["population"] == "b_cell")].iloc[0]
    assert row["total_count"] == 93214
    assert row["count"] == 10908
    assert row["percentage"] == pytest.approx(11.70)


def test_percentages_sum_to_100_per_sample(db: Path) -> None:
    table = relative_frequency_table(db)
    sums = table.groupby("sample")["percentage"].sum()
    assert sums.min() == pytest.approx(100.0, abs=0.05)
    assert sums.max() == pytest.approx(100.0, abs=0.05)


def test_missing_db_raises(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.db"
    with pytest.raises(FileNotFoundError):
        relative_frequency_table(missing)


def test_zero_total_sample_yields_null_percentage(tmp_path: Path) -> None:
    # One sample whose five population counts are all zero. The view divides by
    # NULLIF(total, 0), so the total is zero and every percentage is NULL rather
    # than a divide error.
    path = tmp_path / "zero.db"
    conn = sqlite3.connect(path)
    try:
        conn.executescript(load_data.SCHEMA)
        with conn:
            conn.execute("INSERT INTO project VALUES (1, 'prj')")
            conn.execute("INSERT INTO subject VALUES (1, 'subj', 1, 'healthy', 'F', 40)")
            conn.execute("INSERT INTO treatment_episode VALUES (1, 1, 'none', NULL)")
            conn.execute("INSERT INTO sample VALUES (1, 'sample_zero', 1, 'PBMC', 0)")
            conn.executemany(
                "INSERT INTO measurement VALUES (1, ?, 0)",
                [(pop,) for pop in load_data.POPULATIONS],
            )
    finally:
        conn.close()

    table = relative_frequency_table(path)
    assert len(table) == len(load_data.POPULATIONS)
    assert (table["total_count"] == 0).all()
    assert table["percentage"].isna().all()


def test_write_csv(db: Path, tmp_path: Path) -> None:
    out_path = tmp_path / "outputs" / "relative_frequencies.csv"
    returned = write_relative_frequency_csv(out_path, db)
    assert returned == out_path
    assert out_path.exists()

    written = pd.read_csv(out_path)
    assert list(written.columns) == OUTPUT_COLUMNS
    assert len(written) == 52500
