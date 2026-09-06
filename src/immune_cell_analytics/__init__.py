"""Immune Cell Analytics.

Tools for summarizing immune cell population counts as relative frequencies
and comparing treatment responders against non-responders.
"""

__version__ = "0.1.0"

# The five immune cell populations measured in the dataset.
CELL_POPULATIONS: tuple[str, ...] = (
    "b_cell",
    "cd8_t_cell",
    "cd4_t_cell",
    "nk_cell",
    "monocyte",
)
