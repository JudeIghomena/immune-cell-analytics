"""Baseline subset analysis for the fixed study cohort.

The subset is the baseline slice of the study cohort: melanoma subjects treated
with miraclib, PBMC samples, taken at time_from_treatment_start = 0. The cohort
filter itself is the shared COHORT_WHERE fragment, so it is defined in one place
and this module only adds the baseline timepoint on top.

From that subset three breakdowns are reported. Samples per project counts
samples, so it uses COUNT(*). Subjects by response and subjects by sex count
distinct subjects, because a subject could contribute more than one sample.

This module reads data only. It writes files from main, so the query functions
stay easy to test on a temporary database.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from . import COHORT_WHERE

DEFAULT_DB = Path(__file__).resolve().parents[2] / "cell_count.db"

# The subset is the single sample per subject taken at treatment start.
_BASELINE_TIMEPOINT = 0

# The baseline subset sample list. Columns: sample, subject, project, response,
# sex. The cohort filter is shared, the baseline timepoint is added here.
_SAMPLES_QUERY = f"""
SELECT
    sa.sample_code  AS sample,
    su.subject_code AS subject,
    p.project_code  AS project,
    te.response,
    su.sex
FROM sample sa
JOIN treatment_episode te ON te.episode_id = sa.episode_id
JOIN subject su           ON su.subject_id = te.subject_id
JOIN project p            ON p.project_id = su.project_id
WHERE {COHORT_WHERE}
  AND sa.time_from_treatment_start = {_BASELINE_TIMEPOINT}
ORDER BY sa.sample_code
"""


def baseline_cohort_samples(db_path: Path = DEFAULT_DB) -> pd.DataFrame:
    """Return the baseline subset sample list, one row per sample.

    The columns are sample, subject, project, response, sex, ordered by sample.

    Raises
    ------
    FileNotFoundError
        If db_path does not exist.
    """
    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found: {db_path}. Run 'python load_data.py' to build it."
        )
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql(_SAMPLES_QUERY, conn)


def samples_per_project(db_path: Path = DEFAULT_DB) -> pd.DataFrame:
    """Return the number of samples per project, ordered by project.

    The columns are project, n_samples. Samples are counted, so a project with
    two samples from one subject contributes two.
    """
    samples = baseline_cohort_samples(db_path)
    counts = samples.groupby("project", as_index=False).agg(n_samples=("sample", "size"))
    return counts.sort_values("project").reset_index(drop=True)


def subjects_by_response(db_path: Path = DEFAULT_DB) -> pd.DataFrame:
    """Return the number of distinct subjects per response, ordered by response.

    The columns are response, n_subjects. Subjects are counted distinctly, so a
    subject with more than one baseline sample is counted once.
    """
    samples = baseline_cohort_samples(db_path)
    counts = samples.groupby("response", as_index=False).agg(n_subjects=("subject", "nunique"))
    return counts.sort_values("response").reset_index(drop=True)


def subjects_by_sex(db_path: Path = DEFAULT_DB) -> pd.DataFrame:
    """Return the number of distinct subjects per sex, ordered by sex.

    The columns are sex, n_subjects. Subjects are counted distinctly, so a
    subject with more than one baseline sample is counted once.
    """
    samples = baseline_cohort_samples(db_path)
    counts = samples.groupby("sex", as_index=False).agg(n_subjects=("subject", "nunique"))
    return counts.sort_values("sex").reset_index(drop=True)


def _write_table(table: pd.DataFrame, out_path: Path) -> Path:
    """Write a table to CSV, creating the parent directory if needed."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_path, index=False)
    return out_path


def main() -> None:
    outputs = DEFAULT_DB.parent / "outputs"

    samples = baseline_cohort_samples()
    by_project = samples_per_project()
    by_response = subjects_by_response()
    by_sex = subjects_by_sex()

    print(f"Baseline subset samples: {len(samples)}")
    print()
    print("Samples per project")
    print(by_project.to_string(index=False))
    print()
    print("Distinct subjects by response")
    print(by_response.to_string(index=False))
    print()
    print("Distinct subjects by sex")
    print(by_sex.to_string(index=False))

    for table, filename in (
        (samples, "subset_samples.csv"),
        (by_project, "subset_by_project.csv"),
        (by_response, "subset_by_response.csv"),
        (by_sex, "subset_by_sex.csv"),
    ):
        _write_table(table, outputs / filename)


if __name__ == "__main__":
    main()
