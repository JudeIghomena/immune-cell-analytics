"""Tests for the responder comparison, corrections, and effect size.

The cohort statistics are computed from a temp database built by
load_data.build_database, so the real root database is never touched. The raw
p-values are stable properties of the data, so they are asserted against known
values within tolerance.
"""

from pathlib import Path

import load_data
import pytest

from immune_cell_analytics.stats import (
    benjamini_hochberg,
    bootstrap_effect_ci,
    cohort_frequencies,
    compare_responders,
    conclusion,
    rank_biserial,
    trajectory_summary,
)

CSV = load_data.find_csv()

# Expected number of subjects in the fixed cohort, per population.
_N_YES = 331
_N_NO = 325
_N_TOTAL = _N_YES + _N_NO

# Known baseline raw p-values, none significant after correction.
_BASELINE_P = {
    "b_cell": 0.55,
    "cd8_t_cell": 0.51,
    "cd4_t_cell": 0.80,
    "nk_cell": 0.89,
    "monocyte": 0.21,
}


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    load_data.build_database(CSV, path)
    return path


def test_benjamini_hochberg_known_values() -> None:
    # Five equally spaced p-values. Each scaled value p * n / rank equals 0.05,
    # so every adjusted value is 0.05.
    adjusted = benjamini_hochberg([0.01, 0.02, 0.03, 0.04, 0.05])
    assert adjusted == pytest.approx([0.05, 0.05, 0.05, 0.05, 0.05])


def test_benjamini_hochberg_monotone_in_input_order() -> None:
    # Input order [0.04, 0.01] with n = 2: the smaller gets 0.01 * 2 / 1 = 0.02,
    # the larger gets 0.04 * 2 / 2 = 0.04.
    assert benjamini_hochberg([0.04, 0.01]) == pytest.approx([0.04, 0.02])


def test_benjamini_hochberg_caps_at_one() -> None:
    assert benjamini_hochberg([0.8, 0.9]) == pytest.approx([0.9, 0.9])


def test_benjamini_hochberg_empty() -> None:
    assert benjamini_hochberg([]) == []


def test_cohort_frequencies_baseline_counts(db: Path) -> None:
    freq = cohort_frequencies(db, "baseline")
    for population in _BASELINE_P:
        sub = freq[freq["population"] == population]
        assert len(sub) == _N_TOTAL
        assert (sub["response"] == "yes").sum() == _N_YES
        assert (sub["response"] == "no").sum() == _N_NO


def test_cohort_frequencies_subject_mean_counts(db: Path) -> None:
    freq = cohort_frequencies(db, "subject_mean")
    for population in _BASELINE_P:
        sub = freq[freq["population"] == population]
        assert len(sub) == _N_TOTAL


def test_cohort_frequencies_bad_unit_raises(db: Path) -> None:
    with pytest.raises(ValueError, match="unit must be"):
        cohort_frequencies(db, "all_timepoints")  # type: ignore[arg-type]


def test_cohort_frequencies_missing_db_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        cohort_frequencies(tmp_path / "missing.db", "baseline")


def test_compare_responders_baseline_p_values(db: Path) -> None:
    results = compare_responders(db, "baseline").set_index("population")
    for population, expected in _BASELINE_P.items():
        assert results.loc[population, "p_raw"] == pytest.approx(expected, abs=0.01)
    assert not results["significant"].any()
    assert (results["n_yes"] == _N_YES).all()
    assert (results["n_no"] == _N_NO).all()


def test_compare_responders_subject_mean_cd4(db: Path) -> None:
    results = compare_responders(db, "subject_mean").set_index("population")
    assert results.loc["cd4_t_cell", "p_raw"] == pytest.approx(0.012, abs=0.002)
    # Raw p is below 0.05 but the adjusted p is not, so it is not significant.
    assert results.loc["cd4_t_cell", "p_adj"] == pytest.approx(0.06, abs=0.01)
    assert not results.loc["cd4_t_cell", "significant"]


def test_compare_responders_column_order(db: Path) -> None:
    results = compare_responders(db, "baseline")
    assert list(results.columns) == [
        "population",
        "n_yes",
        "n_no",
        "median_yes",
        "median_no",
        "u_stat",
        "p_raw",
        "p_adj",
        "effect_size",
        "significant",
    ]
    assert list(results["population"]) == [
        "b_cell",
        "cd8_t_cell",
        "cd4_t_cell",
        "nk_cell",
        "monocyte",
    ]


def test_rank_biserial_formula() -> None:
    # U equal to half of n_yes * n_no means complete overlap, effect size 0.
    assert rank_biserial(50.0, 10, 10) == pytest.approx(0.0)
    # U at the maximum means the yes group dominates, effect size 1.
    assert rank_biserial(100.0, 10, 10) == pytest.approx(1.0)
    # U at zero means the yes group is dominated, effect size -1.
    assert rank_biserial(0.0, 10, 10) == pytest.approx(-1.0)


def test_rank_biserial_empty_group_raises() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        rank_biserial(0.0, 0, 5)


def test_conclusion_reports_none_significant(db: Path) -> None:
    results = compare_responders(db, "baseline")
    text = conclusion(results, "baseline")
    assert "no immune cell population differs significantly" in text
    assert "\u2014" not in text  # no em dash


def test_trajectory_summary_shape_and_counts(db: Path) -> None:
    summary = trajectory_summary(db)
    # Three timepoints and two responses for each of the five populations.
    assert len(summary) == len(_BASELINE_P) * 3 * 2
    for population in _BASELINE_P:
        panel = summary[summary["population"] == population]
        assert sorted(panel["timepoint"].unique()) == [0, 7, 14]
        assert set(panel["response"]) == {"yes", "no"}
        yes = panel[panel["response"] == "yes"]
        no = panel[panel["response"] == "no"]
        assert (yes["n"] == _N_YES).all()
        assert (no["n"] == _N_NO).all()
        assert panel["mean"].notna().all()
        assert panel["sem"].notna().all()
        assert (panel["ci_half"] >= 0).all()


def test_bootstrap_effect_ci_deterministic() -> None:
    yes = [1.0, 2.0, 3.0, 4.0, 5.0]
    no = [2.0, 3.0, 4.0, 5.0, 6.0]
    first = bootstrap_effect_ci(yes, no, n_boot=300, seed=0)
    second = bootstrap_effect_ci(yes, no, n_boot=300, seed=0)
    assert first == second


def test_bootstrap_effect_ci_brackets_point_estimate(db: Path) -> None:
    freq = cohort_frequencies(db, "baseline")
    sub = freq[freq["population"] == "cd4_t_cell"]
    yes = sub[sub["response"] == "yes"]["percentage"].to_numpy()
    no = sub[sub["response"] == "no"]["percentage"].to_numpy()
    point = (
        compare_responders(db, "baseline").set_index("population").loc["cd4_t_cell", "effect_size"]
    )
    low, high = bootstrap_effect_ci(yes, no, n_boot=300, seed=0)
    assert low <= point <= high


def test_bootstrap_effect_ci_separated_excludes_zero() -> None:
    yes = [10.0, 11.0, 12.0, 13.0, 14.0]
    no = [1.0, 2.0, 3.0, 4.0, 5.0]
    low, high = bootstrap_effect_ci(yes, no, n_boot=300, seed=0)
    assert low > 0.0
    assert high > 0.0


def test_bootstrap_effect_ci_identical_contains_zero() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    low, high = bootstrap_effect_ci(values, list(values), n_boot=300, seed=0)
    assert low <= 0.0 <= high


def test_bootstrap_effect_ci_empty_group_raises() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        bootstrap_effect_ci([], [1.0, 2.0])
