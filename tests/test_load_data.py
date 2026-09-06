"""Tests for the database loader.

These pin the acceptance criteria from the plan: correct row counts, resolved
foreign keys, structurally-correct NULL responses, and a safe idempotent
re-run. The database is built in a temp directory so the real root database is
never touched.
"""

import sqlite3
from pathlib import Path

import load_data
import pytest

CSV = load_data.find_csv()


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    load_data.build_database(CSV, path)
    return path


def test_row_counts(db: Path) -> None:
    conn = sqlite3.connect(db)
    try:
        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("project", "subject", "treatment_episode", "sample", "measurement")
        }
    finally:
        conn.close()
    assert counts["project"] == 3
    assert counts["subject"] == 3500
    assert counts["treatment_episode"] == 3500
    assert counts["sample"] == 10500
    assert counts["measurement"] == 52500  # 10500 samples * 5 populations


def test_foreign_keys_resolve(db: Path) -> None:
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        conn.close()
    assert violations == []


def test_response_null_only_for_untreated(db: Path) -> None:
    conn = sqlite3.connect(db)
    try:
        null_treated = conn.execute(
            "SELECT COUNT(*) FROM treatment_episode WHERE response IS NULL AND treatment != 'none'"
        ).fetchone()[0]
        nonnull_untreated = conn.execute(
            "SELECT COUNT(*) FROM treatment_episode "
            "WHERE response IS NOT NULL AND treatment = 'none'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert null_treated == 0
    assert nonnull_untreated == 0


def test_percentages_sum_to_100_per_sample(db: Path) -> None:
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT sample_id, SUM(percentage) FROM sample_population_frequency GROUP BY sample_id"
        ).fetchall()
    finally:
        conn.close()
    assert rows
    for _sample_id, total in rows:
        assert total == pytest.approx(100.0, abs=0.01)


def test_idempotent_rerun(tmp_path: Path) -> None:
    path = tmp_path / "rerun.db"
    first = load_data.build_database(CSV, path)
    second = load_data.build_database(CSV, path)
    assert first == second
