"""Responder versus non-responder comparison of population frequencies.

The fixed cohort is melanoma subjects treated with miraclib, PBMC samples. Each
population's relative frequency is compared between responders (response yes) and
non-responders (response no) with a two-sided Mann-Whitney U test, and the five
p-values are corrected together with Benjamini-Hochberg.

Two units of analysis are supported, one value per subject in both:
  baseline      the single sample taken at time_from_treatment_start = 0
  subject_mean  each subject's mean percentage across their timepoints

This module reads data and computes statistics only. It does not plot and it
does not write files except from main, so the functions are easy to test on the
real database.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy.stats import mannwhitneyu

from . import CELL_POPULATIONS

DEFAULT_DB = Path(__file__).resolve().parents[2] / "cell_count.db"

Unit = Literal["baseline", "subject_mean"]

# One sample per subject sits at this timepoint for the baseline analysis.
_BASELINE_TIMEPOINT = 0

# A result is called significant only after the multiple-comparison correction.
_ALPHA = 0.05

# Normal approximation multiplier for a 95 percent confidence interval.
_Z_95 = 1.96

# Every cohort row, all timepoints, for the fixed melanoma + miraclib + PBMC
# cohort. The baseline and subject_mean units are derived from this in pandas.
_COHORT_QUERY = """
SELECT
    su.subject_code AS subject,
    v.population,
    v.percentage,
    te.response,
    sa.time_from_treatment_start AS timepoint
FROM sample_population_frequency v
JOIN sample sa            ON sa.sample_id = v.sample_id
JOIN treatment_episode te ON te.episode_id = sa.episode_id
JOIN subject su           ON su.subject_id = te.subject_id
WHERE su.condition = 'melanoma'
  AND te.treatment = 'miraclib'
  AND sa.sample_type = 'PBMC'
"""

_STATS_COLUMNS = [
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


def benjamini_hochberg(pvalues: list[float]) -> list[float]:
    """Return Benjamini-Hochberg adjusted p-values in the input order.

    Adjusted values are capped at 1.0 and made monotone non-decreasing across
    ascending raw p-values, which is the standard step-up procedure. An empty
    input returns an empty list.
    """
    n = len(pvalues)
    if n == 0:
        return []

    order = sorted(range(n), key=lambda i: pvalues[i])
    adjusted = [0.0] * n
    running_min = 1.0
    for rank in range(n, 0, -1):
        i = order[rank - 1]
        scaled = pvalues[i] * n / rank
        running_min = min(running_min, scaled)
        adjusted[i] = min(running_min, 1.0)
    return adjusted


def _read_cohort(db_path: Path) -> pd.DataFrame:
    """Return every cohort row across all timepoints from the database.

    The columns are subject, population, percentage, response, timepoint.

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
        return pd.read_sql(_COHORT_QUERY, conn)


def cohort_frequencies(db_path: Path = DEFAULT_DB, unit: Unit = "baseline") -> pd.DataFrame:
    """Return one percentage per subject per population, with a response label.

    The columns are subject, population, response, percentage, sorted by
    population then subject. For unit baseline the value is the subject's
    time_from_treatment_start = 0 sample. For unit subject_mean it is the mean
    percentage across all of the subject's timepoints.

    Raises
    ------
    FileNotFoundError
        If db_path does not exist.
    ValueError
        If unit is not baseline or subject_mean.
    """
    if unit not in ("baseline", "subject_mean"):
        raise ValueError(f"unit must be 'baseline' or 'subject_mean', got {unit!r}")

    rows = _read_cohort(db_path)

    if unit == "baseline":
        frame = rows.loc[rows["timepoint"] == _BASELINE_TIMEPOINT, :]
        frame = frame[["subject", "population", "response", "percentage"]].copy()
    else:
        frame = rows.groupby(["subject", "population", "response"], as_index=False).agg(
            percentage=("percentage", "mean")
        )

    return frame.sort_values(["population", "subject"]).reset_index(drop=True)


def trajectory_summary(db_path: Path = DEFAULT_DB) -> pd.DataFrame:
    """Summarize each population's frequency over time by response group.

    Uses every timepoint in the cohort. Returns one row per population per
    timepoint per response with columns population, timepoint, response, mean,
    sem, ci_half, n. mean is the mean relative frequency percentage, sem is its
    standard error (standard deviation divided by the square root of n), ci_half
    is the 95 percent confidence interval half-width (1.96 times sem), and n is
    the number of samples. Rows are sorted by population, timepoint, response.

    Each timepoint holds one sample per subject, so the samples within a
    timepoint are independent and the standard error is well defined.

    Raises
    ------
    FileNotFoundError
        If db_path does not exist.
    """
    rows = _read_cohort(db_path)
    summary = rows.groupby(["population", "timepoint", "response"], as_index=False).agg(
        mean=("percentage", "mean"),
        sem=("percentage", "sem"),
        n=("percentage", "size"),
    )
    summary["ci_half"] = _Z_95 * summary["sem"]
    return summary.sort_values(["population", "timepoint", "response"]).reset_index(drop=True)


def compare_responders(db_path: Path = DEFAULT_DB, unit: Unit = "baseline") -> pd.DataFrame:
    """Compare responders against non-responders for each population.

    Returns one row per population, ordered by the reported population order,
    with columns population, n_yes, n_no, median_yes, median_no, u_stat, p_raw,
    p_adj, effect_size, significant. The test is a two-sided Mann-Whitney U, the
    effect size is the rank-biserial correlation, and significant is True when
    the Benjamini-Hochberg adjusted p-value is below 0.05.
    """
    freq = cohort_frequencies(db_path, unit)

    records: list[dict[str, object]] = []
    for population in CELL_POPULATIONS:
        sub = freq.loc[freq["population"] == population]
        yes = sub.loc[sub["response"] == "yes", "percentage"]
        no = sub.loc[sub["response"] == "no", "percentage"]
        u_stat, p_raw = mannwhitneyu(yes, no, alternative="two-sided")
        records.append(
            {
                "population": population,
                "n_yes": len(yes),
                "n_no": len(no),
                "median_yes": float(yes.median()),
                "median_no": float(no.median()),
                "u_stat": float(u_stat),
                "p_raw": float(p_raw),
                "effect_size": rank_biserial(float(u_stat), len(yes), len(no)),
            }
        )

    adjusted = benjamini_hochberg([r["p_raw"] for r in records])  # type: ignore[misc]
    for record, p_adj in zip(records, adjusted, strict=True):
        record["p_adj"] = p_adj
        record["significant"] = p_adj < _ALPHA

    return pd.DataFrame(records, columns=_STATS_COLUMNS)


def rank_biserial(u_stat: float, n_yes: int, n_no: int) -> float:
    """Return the rank-biserial effect size for a Mann-Whitney U statistic.

    The value is 2U / (n_yes * n_no) - 1, where U is the statistic for the yes
    group. It ranges from -1 to 1, with 0 meaning the two groups' distributions
    overlap completely. A positive value means responders (yes) tend to be
    higher, a negative value means responders tend to be lower. Raises
    ValueError if either group is empty.
    """
    if n_yes == 0 or n_no == 0:
        raise ValueError("Both groups must be non-empty to compute an effect size.")
    return 2.0 * u_stat / (n_yes * n_no) - 1.0


def bootstrap_effect_ci(
    yes_values: npt.ArrayLike,
    no_values: npt.ArrayLike,
    n_boot: int = 2000,
    seed: int = 0,
) -> tuple[float, float]:
    """Return a bootstrap 95 percent confidence interval for the effect size.

    Each group is resampled with replacement n_boot times, the rank-biserial
    effect size is recomputed on each resample, and the 2.5 and 97.5 percentiles
    of those values are returned as the interval bounds. The sign convention
    matches rank_biserial: positive means responders tend to be higher. The
    result is deterministic for a given seed via numpy's default generator.

    Raises
    ------
    ValueError
        If either group is empty.
    """
    yes = np.asarray(yes_values, dtype=float)
    no = np.asarray(no_values, dtype=float)
    if yes.size == 0 or no.size == 0:
        raise ValueError("Both groups must be non-empty to bootstrap an effect size.")

    rng = np.random.default_rng(seed)
    effects = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        resampled_yes = rng.choice(yes, size=yes.size, replace=True)
        resampled_no = rng.choice(no, size=no.size, replace=True)
        u_stat, _ = mannwhitneyu(resampled_yes, resampled_no, alternative="two-sided")
        effects[i] = rank_biserial(float(u_stat), yes.size, no.size)

    low, high = np.percentile(effects, [2.5, 97.5])
    return float(low), float(high)


def conclusion(results: pd.DataFrame, unit: Unit) -> str:
    """Return a plain-language summary of which populations are significant.

    The summary names the unit of analysis and lists any population significant
    after Benjamini-Hochberg correction, with the direction of the difference in
    medians. It states plainly when no population is significant.
    """
    label = "baseline (one sample per subject at treatment start)"
    if unit == "subject_mean":
        label = "subject mean (each subject averaged across timepoints)"

    significant = results.loc[results["significant"]]
    if significant.empty:
        return (
            f"In the {label} analysis, no immune cell population differs significantly "
            f"between responders and non-responders after Benjamini-Hochberg correction "
            f"(all adjusted p at or above {_ALPHA})."
        )

    parts: list[str] = []
    for _, row in significant.iterrows():
        higher = "higher" if row["median_yes"] > row["median_no"] else "lower"
        parts.append(
            f"{row['population']} is {higher} in responders (adjusted p {row['p_adj']:.3f})"
        )
    return (
        f"In the {label} analysis, {len(significant)} population(s) differ significantly "
        f"between responders and non-responders after Benjamini-Hochberg correction: "
        f"{'; '.join(parts)}."
    )


def _write_table(results: pd.DataFrame, out_path: Path) -> Path:
    """Write a stats table to CSV, creating the parent directory if needed."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(out_path, index=False)
    return out_path


def main() -> None:
    from .plots import (
        effect_size_forest_plot,
        responder_boxplot,
        responder_trajectory_plot,
    )

    outputs = DEFAULT_DB.parent / "outputs"

    units: tuple[tuple[Unit, str], ...] = (
        ("baseline", "responder_stats_baseline.csv"),
        ("subject_mean", "responder_stats_subject_mean.csv"),
    )
    for unit, filename in units:
        results = compare_responders(unit=unit)
        _write_table(results, outputs / filename)
        print(f"=== {unit} ===")
        print(results.to_string(index=False))
        print(conclusion(results, unit))
        print()

    figures = (
        responder_boxplot(DEFAULT_DB, outputs / "responder_boxplot.png", unit="baseline"),
        responder_trajectory_plot(DEFAULT_DB, outputs / "responder_trajectory.png"),
        effect_size_forest_plot(
            DEFAULT_DB, outputs / "responder_effect_forest.png", unit="baseline"
        ),
    )
    for figure_path in figures:
        print(f"Wrote figure {figure_path}")


if __name__ == "__main__":
    main()
