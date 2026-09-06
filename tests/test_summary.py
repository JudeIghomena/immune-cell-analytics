"""Tests for relative-frequency summarization."""

import pandas as pd
import pytest

from immune_cell_analytics import CELL_POPULATIONS
from immune_cell_analytics.summary import SUMMARY_COLUMNS, relative_frequency_summary


def _frame(**counts: int) -> pd.DataFrame:
    row = {"sample": "s1"}
    row.update(dict.fromkeys(CELL_POPULATIONS, 0))
    row.update(counts)
    return pd.DataFrame([row])


def test_percentages_sum_to_100_per_sample() -> None:
    df = _frame(b_cell=10, cd8_t_cell=20, cd4_t_cell=30, nk_cell=25, monocyte=15)
    out = relative_frequency_summary(df)
    assert list(out.columns) == list(SUMMARY_COLUMNS)
    assert out["percentage"].sum() == pytest.approx(100.0)
    assert (out["total_count"] == 100).all()


def test_known_percentage_value() -> None:
    df = _frame(b_cell=25, cd8_t_cell=25, cd4_t_cell=25, nk_cell=25, monocyte=0)
    out = relative_frequency_summary(df)
    b_cell = out.loc[out["population"] == "b_cell", "percentage"].iloc[0]
    assert b_cell == pytest.approx(25.0)


def test_one_row_per_population() -> None:
    df = _frame(b_cell=1)
    out = relative_frequency_summary(df)
    assert len(out) == len(CELL_POPULATIONS)


def test_empty_sample_does_not_divide_by_zero() -> None:
    df = _frame()  # all populations zero
    out = relative_frequency_summary(df)
    assert (out["percentage"] == 0.0).all()
