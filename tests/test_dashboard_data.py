"""Tests for the dashboard data-access helpers.

Both helpers are exercised against a temporary database built by
load_data.build_database, so the real root database is never touched. Row counts
and one known percentage are stable properties of the data, so they are asserted
against known values.
"""

from pathlib import Path

import load_data
import pytest

from immune_cell_analytics.dashboard_data import (
    frequency_with_metadata,
    sample_metadata,
)

CSV = load_data.find_csv()

# Known counts for the whole dataset and the clinical baseline cohort.
_N_FREQUENCY_ROWS = 52_500
_N_SAMPLE_ROWS = 10_500
_N_COHORT_SAMPLES = 656
_N_POPULATIONS = 5

_FREQUENCY_COLUMNS = [
    "sample",
    "project",
    "condition",
    "sex",
    "treatment",
    "response",
    "sample_type",
    "timepoint",
    "subject",
    "population",
    "count",
    "total_count",
    "percentage",
]
_METADATA_COLUMNS = [
    "sample",
    "project",
    "condition",
    "sex",
    "treatment",
    "response",
    "sample_type",
    "timepoint",
    "subject",
]


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    load_data.build_database(CSV, path)
    return path


def test_frequency_shape_and_columns(db: Path) -> None:
    freq = frequency_with_metadata(db)
    assert len(freq) == _N_FREQUENCY_ROWS
    assert list(freq.columns) == _FREQUENCY_COLUMNS


def test_frequency_percentage_matches_view(db: Path) -> None:
    freq = frequency_with_metadata(db)
    row = freq.loc[(freq["sample"] == "sample00000") & (freq["population"] == "b_cell")]
    assert len(row) == 1
    assert row["percentage"].iloc[0] == pytest.approx(11.70, abs=0.01)


def test_frequency_cohort_filter(db: Path) -> None:
    freq = frequency_with_metadata(db)
    cohort = freq.loc[
        (freq["condition"] == "melanoma")
        & (freq["treatment"] == "miraclib")
        & (freq["sample_type"] == "PBMC")
        & (freq["timepoint"] == 0)
    ]
    assert len(cohort) == _N_COHORT_SAMPLES * _N_POPULATIONS


def test_sample_metadata_shape_and_columns(db: Path) -> None:
    meta = sample_metadata(db)
    assert len(meta) == _N_SAMPLE_ROWS
    assert list(meta.columns) == _METADATA_COLUMNS


def test_sample_metadata_cohort_filter(db: Path) -> None:
    meta = sample_metadata(db)
    cohort = meta.loc[
        (meta["condition"] == "melanoma")
        & (meta["treatment"] == "miraclib")
        & (meta["sample_type"] == "PBMC")
        & (meta["timepoint"] == 0)
    ]
    assert len(cohort) == _N_COHORT_SAMPLES
    assert cohort["subject"].nunique() == _N_COHORT_SAMPLES


def test_frequency_missing_db_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        frequency_with_metadata(tmp_path / "missing.db")


def test_sample_metadata_missing_db_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        sample_metadata(tmp_path / "missing.db")
