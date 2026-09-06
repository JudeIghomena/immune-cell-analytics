"""Initialize the SQLite database and load the cell-count data.

Run it directly, with no arguments:

    python load_data.py

It creates cell_count.db in the repository root and loads every row from
cell-count.csv into a normalized relational schema. Re-running rebuilds a clean
database from the CSV, so the script is safe to run repeatedly.

The script is self-contained. It needs only pandas and the standard library, so
it runs without installing the project package.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "cell_count.db"

# The dataset may live in the repo root or under data/. Prefer data/.
CSV_CANDIDATES = (ROOT / "data" / "cell-count.csv", ROOT / "cell-count.csv")

# The five immune cell populations, in the order reported.
POPULATIONS = ("b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte")

# Metadata columns the loader relies on, by their real names in the CSV.
REQUIRED_COLUMNS = (
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
    *POPULATIONS,
)

SCHEMA = """
CREATE TABLE project (
    project_id   INTEGER PRIMARY KEY,
    project_code TEXT NOT NULL UNIQUE
);

CREATE TABLE subject (
    subject_id   INTEGER PRIMARY KEY,
    subject_code TEXT NOT NULL UNIQUE,
    project_id   INTEGER NOT NULL REFERENCES project(project_id),
    condition    TEXT NOT NULL CHECK (condition IN ('melanoma','carcinoma','healthy')),
    sex          TEXT NOT NULL CHECK (sex IN ('M','F')),
    age          INTEGER NOT NULL CHECK (age >= 0 AND age <= 120)
);

CREATE TABLE treatment_episode (
    episode_id INTEGER PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES subject(subject_id),
    treatment  TEXT NOT NULL CHECK (treatment IN ('miraclib','phauximab','none')),
    response   TEXT,
    UNIQUE (subject_id, treatment),
    CHECK ((treatment = 'none' AND response IS NULL)
        OR (treatment <> 'none' AND response IS NOT NULL AND response IN ('yes','no')))
);

CREATE TABLE sample (
    sample_id                 INTEGER PRIMARY KEY,
    sample_code               TEXT NOT NULL UNIQUE,
    episode_id                INTEGER NOT NULL REFERENCES treatment_episode(episode_id),
    sample_type               TEXT NOT NULL CHECK (sample_type IN ('PBMC','WB')),
    time_from_treatment_start INTEGER NOT NULL CHECK (time_from_treatment_start >= 0)
);

CREATE TABLE measurement (
    sample_id  INTEGER NOT NULL REFERENCES sample(sample_id),
    population TEXT NOT NULL CHECK (population IN
                 ('b_cell','cd8_t_cell','cd4_t_cell','nk_cell','monocyte')),
    count      INTEGER NOT NULL CHECK (count >= 0),
    PRIMARY KEY (sample_id, population)
);

CREATE VIEW sample_population_frequency AS
SELECT
    s.sample_code,
    m.sample_id,
    m.population,
    m.count,
    SUM(m.count) OVER (PARTITION BY m.sample_id) AS total_count,
    100.0 * m.count
        / NULLIF(SUM(m.count) OVER (PARTITION BY m.sample_id), 0) AS percentage
FROM measurement m
JOIN sample s ON s.sample_id = m.sample_id;

CREATE INDEX idx_subject_project   ON subject(project_id);
CREATE INDEX idx_subject_condition ON subject(condition);
CREATE INDEX idx_episode_subject   ON treatment_episode(subject_id);
CREATE INDEX idx_episode_response  ON treatment_episode(response);
CREATE INDEX idx_sample_episode    ON sample(episode_id);
CREATE INDEX idx_sample_filters    ON sample(sample_type, time_from_treatment_start);
"""


def find_csv() -> Path:
    """Return the first cell-count.csv that exists, or raise a clear error."""
    for path in CSV_CANDIDATES:
        if path.exists():
            return path
    searched = ", ".join(str(p) for p in CSV_CANDIDATES)
    raise FileNotFoundError(f"cell-count.csv not found. Looked in: {searched}")


def read_and_validate(csv_path: Path) -> pd.DataFrame:
    """Load the CSV and confirm the required columns are present."""
    df = pd.read_csv(csv_path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in {csv_path.name}: {missing}")
    if df["sample"].duplicated().any():
        raise ValueError("Duplicate sample identifiers found in the CSV.")

    # The loader collapses each subject to one row (one treatment episode) and
    # to one set of static attributes. Fail loudly if the data breaks that,
    # rather than silently dropping a second treatment or attribute set.
    multi_treatment = df.groupby("subject")["treatment"].nunique()
    offenders = multi_treatment[multi_treatment > 1].index.tolist()
    if offenders:
        raise ValueError(
            f"Subjects with more than one treatment are not supported: {offenders[:5]}"
        )

    # nunique ignores NaN by default, so an untreated subject whose response is
    # blank in every row counts as zero distinct values, not an inconsistency.
    static_cols = ["project", "condition", "sex", "age", "response"]
    varying = df.groupby("subject")[static_cols].nunique()
    inconsistent = varying[(varying > 1).any(axis=1)].index.tolist()
    if inconsistent:
        raise ValueError(
            f"Subjects with inconsistent attributes across samples: {inconsistent[:5]}"
        )

    return df


def _clean_response(value: object) -> str | None:
    """Map a blank or missing response to NULL, otherwise keep the value."""
    if value is None or (isinstance(value, float) and pd.isna(value)) or value == "":
        return None
    return str(value)


def build_database(csv_path: Path, db_path: Path) -> dict[str, int]:
    """Create the schema and load every row. Returns row counts per table.

    The load is idempotent: any existing database at db_path is removed first,
    so each run produces a clean database from the CSV.
    """
    df = read_and_validate(csv_path)

    # Assign surrogate keys deterministically in pandas, so child rows can
    # reference their parents without a round trip to the database.
    project_codes = sorted(df["project"].unique())
    project_id_by_code = {code: i + 1 for i, code in enumerate(project_codes)}

    subjects = (
        df[["subject", "project", "condition", "sex", "age", "treatment", "response"]]
        .drop_duplicates("subject")
        .sort_values("subject")
        .reset_index(drop=True)
    )
    subjects["subject_id"] = subjects.index + 1
    # One treatment episode per subject, so the episode key tracks the subject.
    subjects["episode_id"] = subjects.index + 1
    episode_id_by_subject = dict(zip(subjects["subject"], subjects["episode_id"], strict=True))

    samples = (
        df[["sample", "subject", "sample_type", "time_from_treatment_start"]]
        .sort_values("sample")
        .reset_index(drop=True)
    )
    samples["sample_id"] = samples.index + 1
    samples["episode_id"] = samples["subject"].map(episode_id_by_subject)
    sample_id_by_code = dict(zip(samples["sample"], samples["sample_id"], strict=True))

    measurements = df[["sample", *POPULATIONS]].melt(
        id_vars="sample", var_name="population", value_name="count"
    )
    measurements["sample_id"] = measurements["sample"].map(sample_id_by_code)

    # Assemble parameter rows for executemany. Using tolist gives plain Python
    # scalars, which sqlite3 accepts, unlike numpy integer types.
    project_rows = [(project_id_by_code[c], c) for c in project_codes]
    subject_rows = list(
        zip(
            subjects["subject_id"].tolist(),
            subjects["subject"].tolist(),
            subjects["project"].map(project_id_by_code).tolist(),
            subjects["condition"].tolist(),
            subjects["sex"].tolist(),
            subjects["age"].astype(int).tolist(),
            strict=True,
        )
    )
    episode_rows = list(
        zip(
            subjects["episode_id"].tolist(),
            subjects["subject_id"].tolist(),
            subjects["treatment"].tolist(),
            [_clean_response(v) for v in subjects["response"].tolist()],
            strict=True,
        )
    )
    sample_rows = list(
        zip(
            samples["sample_id"].tolist(),
            samples["sample"].tolist(),
            samples["episode_id"].astype(int).tolist(),
            samples["sample_type"].tolist(),
            samples["time_from_treatment_start"].astype(int).tolist(),
            strict=True,
        )
    )
    measurement_rows = list(
        zip(
            measurements["sample_id"].astype(int).tolist(),
            measurements["population"].tolist(),
            measurements["count"].astype(int).tolist(),
            strict=True,
        )
    )

    db_path.unlink(missing_ok=True)  # idempotent rebuild
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA)
        with conn:  # one transaction, parents before children
            conn.executemany("INSERT INTO project VALUES (?, ?)", project_rows)
            conn.executemany("INSERT INTO subject VALUES (?, ?, ?, ?, ?, ?)", subject_rows)
            conn.executemany("INSERT INTO treatment_episode VALUES (?, ?, ?, ?)", episode_rows)
            conn.executemany("INSERT INTO sample VALUES (?, ?, ?, ?, ?)", sample_rows)
            conn.executemany("INSERT INTO measurement VALUES (?, ?, ?)", measurement_rows)

        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("project", "subject", "treatment_episode", "sample", "measurement")
        }
    finally:
        conn.close()
    return counts


def main() -> None:
    csv_path = find_csv()
    counts = build_database(csv_path, DB_PATH)
    print(f"Loaded {csv_path.name} into {DB_PATH.name}")
    for table, n in counts.items():
        print(f"  {table}: {n} rows")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
