"""Data-access helpers for the interactive dashboard.

Two read-only queries back the dashboard. Both return a tidy pandas frame and
read only from the database, so they are pure and easy to test on a temporary
database. The dashboard script imports these and adds the presentation layer.

Relative frequency comes from the sample_population_frequency view, so the
percentage has a single source and is never recomputed here.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

DEFAULT_DB = Path(__file__).resolve().parents[2] / "cell_count.db"

# Every frequency row joined to its sample, subject, treatment and project
# metadata. The percentage, count and total_count come straight from the view.
_FREQUENCY_QUERY = """
SELECT
    v.sample_code                 AS sample,
    p.project_code                AS project,
    su.condition                  AS condition,
    su.sex                        AS sex,
    te.treatment                  AS treatment,
    te.response                   AS response,
    sa.sample_type                AS sample_type,
    sa.time_from_treatment_start  AS timepoint,
    su.subject_code               AS subject,
    v.population                  AS population,
    v.count                       AS count,
    v.total_count                 AS total_count,
    v.percentage                  AS percentage
FROM sample_population_frequency v
JOIN sample sa            ON sa.sample_id = v.sample_id
JOIN treatment_episode te ON te.episode_id = sa.episode_id
JOIN subject su           ON su.subject_id = te.subject_id
JOIN project p            ON p.project_id = su.project_id
ORDER BY v.sample_code, v.population
"""

# One row per sample with its metadata, no population columns.
_SAMPLE_METADATA_QUERY = """
SELECT
    sa.sample_code                AS sample,
    p.project_code                AS project,
    su.condition                  AS condition,
    su.sex                        AS sex,
    te.treatment                  AS treatment,
    te.response                   AS response,
    sa.sample_type                AS sample_type,
    sa.time_from_treatment_start  AS timepoint,
    su.subject_code               AS subject
FROM sample sa
JOIN treatment_episode te ON te.episode_id = sa.episode_id
JOIN subject su           ON su.subject_id = te.subject_id
JOIN project p            ON p.project_id = su.project_id
ORDER BY sa.sample_code
"""


def _read(query: str, db_path: Path) -> pd.DataFrame:
    """Run a read-only query and return the result frame.

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
        return pd.read_sql(query, conn)


def frequency_with_metadata(db_path: Path = DEFAULT_DB) -> pd.DataFrame:
    """Return the frequency view joined to sample, subject and project metadata.

    Each row is one population in one sample. The columns are sample, project,
    condition, sex, treatment, response, sample_type, timepoint, subject,
    population, count, total_count, percentage. The percentage comes from the
    view, so it is not recomputed here. Rows are ordered by sample then
    population.

    Raises
    ------
    FileNotFoundError
        If db_path does not exist.
    """
    return _read(_FREQUENCY_QUERY, db_path)


def sample_metadata(db_path: Path = DEFAULT_DB) -> pd.DataFrame:
    """Return one row per sample with its metadata.

    The columns are sample, project, condition, sex, treatment, response,
    sample_type, timepoint, subject. Rows are ordered by sample.

    Raises
    ------
    FileNotFoundError
        If db_path does not exist.
    """
    return _read(_SAMPLE_METADATA_QUERY, db_path)
