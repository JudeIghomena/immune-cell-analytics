"""Tests for dataset loading and validation."""

from pathlib import Path

import pandas as pd
import pytest

from immune_cell_analytics import CELL_POPULATIONS
from immune_cell_analytics.io import load_cell_counts

DATASET = Path(__file__).resolve().parents[1] / "data" / "cell-count.csv"


def _valid_row(sample: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "project": "prj1",
        "subject": "sbj000",
        "condition": "melanoma",
        "age": 57,
        "sex": "M",
        "treatment": "miraclib",
        "response": "no",
        "sample": sample,
        "sample_type": "PBMC",
        "time_from_treatment_start": 0,
    }
    row.update(dict.fromkeys(CELL_POPULATIONS, 100))
    row.update(overrides)
    return row


def test_loads_real_dataset() -> None:
    df = load_cell_counts(DATASET)
    assert len(df) == 10500
    assert not df["sample"].duplicated().any()


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_cell_counts("does-not-exist.csv")


def test_duplicate_sample_rejected(tmp_path: Path) -> None:
    path = tmp_path / "dupe.csv"
    pd.DataFrame([_valid_row("s1"), _valid_row("s1")]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="Duplicate sample"):
        load_cell_counts(path)


def test_negative_count_rejected(tmp_path: Path) -> None:
    path = tmp_path / "neg.csv"
    pd.DataFrame([_valid_row("s1", b_cell=-1)]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="non-negative"):
        load_cell_counts(path)


def test_missing_column_rejected(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"
    df = pd.DataFrame([_valid_row("s1")]).drop(columns=["monocyte"])
    df.to_csv(path, index=False)
    with pytest.raises(ValueError, match="Missing required columns"):
        load_cell_counts(path)
