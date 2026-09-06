"""Smoke tests: confirm the package imports and core constants are intact.

These give the CI/CD pipeline something meaningful to verify from the very
first commit, so the pipeline is proven green before any feature work lands.
"""

from immune_cell_analytics import CELL_POPULATIONS, __version__


def test_version_is_set() -> None:
    assert __version__ == "0.1.0"


def test_five_cell_populations() -> None:
    assert len(CELL_POPULATIONS) == 5
    assert "cd8_t_cell" in CELL_POPULATIONS
