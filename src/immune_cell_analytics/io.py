"""Loading and validation for the cell-count dataset."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import CELL_POPULATIONS

# Columns every valid cell-count file must carry.
_METADATA_COLUMNS: tuple[str, ...] = (
    "project",
    "subject",
    "condition",
    "age",
    "sex",
    "treatment",
    "response",
    "sample",
    "sample_type",
    "time_from_treatment_start",
)
REQUIRED_COLUMNS: tuple[str, ...] = _METADATA_COLUMNS + CELL_POPULATIONS


def load_cell_counts(path: str | Path) -> pd.DataFrame:
    """Load the cell-count CSV and validate its structure.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    ValueError
        If required columns are missing, a sample identifier is duplicated,
        or any population count is negative.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    df = pd.read_csv(path)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if df["sample"].duplicated().any():
        dupes = df.loc[df["sample"].duplicated(), "sample"].unique().tolist()
        raise ValueError(f"Duplicate sample identifiers: {dupes[:5]}")

    counts = df[list(CELL_POPULATIONS)]
    if (counts < 0).to_numpy().any():
        raise ValueError("Population counts must be non-negative.")

    return df
