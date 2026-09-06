"""Tests for the responder boxplot figure.

The figure is drawn from a temp database built by load_data.build_database, so
the real root database is never touched. The test asserts the file is written
and non-empty, not the pixels, so a safe styling change does not break it.
"""

from pathlib import Path

import load_data
import pytest

from immune_cell_analytics.plots import (
    effect_size_forest_plot,
    responder_boxplot,
    responder_trajectory_plot,
)

CSV = load_data.find_csv()


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    load_data.build_database(CSV, path)
    return path


def test_responder_boxplot_writes_file(db: Path, tmp_path: Path) -> None:
    out_path = tmp_path / "figs" / "responder_boxplot.png"
    returned = responder_boxplot(db, out_path, unit="baseline")
    assert returned == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_responder_boxplot_subject_mean(db: Path, tmp_path: Path) -> None:
    out_path = tmp_path / "figs" / "responder_boxplot_mean.png"
    responder_boxplot(db, out_path, unit="subject_mean")
    assert out_path.stat().st_size > 0


def test_responder_trajectory_plot_writes_file(db: Path, tmp_path: Path) -> None:
    out_path = tmp_path / "figs" / "responder_trajectory.png"
    returned = responder_trajectory_plot(db, out_path)
    assert returned == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_effect_size_forest_plot_writes_file(db: Path, tmp_path: Path) -> None:
    out_path = tmp_path / "figs" / "responder_effect_forest.png"
    returned = effect_size_forest_plot(db, out_path, unit="baseline")
    assert returned == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > 0
