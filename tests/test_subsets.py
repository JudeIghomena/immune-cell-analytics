"""Tests for the baseline subset analysis.

The subset is computed from a temp database built by load_data.build_database,
so the real root database is never touched. Counts are stable properties of the
data, so they are asserted against known values.
"""

from pathlib import Path

import load_data
import pytest

from immune_cell_analytics.subsets import (
    baseline_cohort_samples,
    samples_per_project,
    subjects_by_response,
    subjects_by_sex,
)

CSV = load_data.find_csv()

# Known counts for the baseline subset (melanoma, miraclib, PBMC, timepoint 0).
_N_SAMPLES = 656
_N_PRJ1 = 384
_N_PRJ3 = 272
_N_YES = 331
_N_NO = 325
_N_MALE = 344
_N_FEMALE = 312


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    load_data.build_database(CSV, path)
    return path


def test_baseline_cohort_samples_shape(db: Path) -> None:
    samples = baseline_cohort_samples(db)
    assert len(samples) == _N_SAMPLES
    assert list(samples.columns) == ["sample", "subject", "project", "response", "sex"]
    assert list(samples["sample"]) == sorted(samples["sample"])


def test_samples_per_project(db: Path) -> None:
    by_project = samples_per_project(db).set_index("project")
    assert list(by_project.columns) == ["n_samples"]
    assert by_project.loc["prj1", "n_samples"] == _N_PRJ1
    assert by_project.loc["prj3", "n_samples"] == _N_PRJ3
    assert "prj2" not in by_project.index


def test_subjects_by_response(db: Path) -> None:
    by_response = subjects_by_response(db).set_index("response")
    assert list(by_response.columns) == ["n_subjects"]
    assert by_response.loc["yes", "n_subjects"] == _N_YES
    assert by_response.loc["no", "n_subjects"] == _N_NO


def test_subjects_by_sex(db: Path) -> None:
    by_sex = subjects_by_sex(db).set_index("sex")
    assert list(by_sex.columns) == ["n_subjects"]
    assert by_sex.loc["M", "n_subjects"] == _N_MALE
    assert by_sex.loc["F", "n_subjects"] == _N_FEMALE


def test_breakdowns_count_distinct_subjects(db: Path) -> None:
    # 2b and 2c count distinct subjects, not samples. Each baseline subject
    # contributes one sample here, so both totals equal the distinct subject
    # count, which is the sample count for this subset.
    samples = baseline_cohort_samples(db)
    distinct_subjects = samples["subject"].nunique()
    assert distinct_subjects == _N_SAMPLES
    assert subjects_by_response(db)["n_subjects"].sum() == distinct_subjects
    assert subjects_by_sex(db)["n_subjects"].sum() == distinct_subjects


def test_missing_db_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        baseline_cohort_samples(tmp_path / "missing.db")


def test_source_has_no_unlisted_treatment() -> None:
    # The only treatments in this dataset are miraclib, none, and phauximab.
    # Guard that no stray, nonexistent treatment name crept into the module.
    source = Path(__import__("immune_cell_analytics.subsets", fromlist=[""]).__file__ or "")
    text = source.read_text(encoding="utf-8")
    assert "quintaz" not in text.lower()
