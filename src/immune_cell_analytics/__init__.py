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

# The fixed study cohort, defined once and reused by every query that needs it:
# melanoma subjects treated with miraclib, PBMC samples. This is a SQL WHERE
# fragment that assumes the joined tables carry these aliases: su for subject,
# te for treatment_episode, sa for sample.
COHORT_WHERE: str = (
    "su.condition = 'melanoma' AND te.treatment = 'miraclib' AND sa.sample_type = 'PBMC'"
)
