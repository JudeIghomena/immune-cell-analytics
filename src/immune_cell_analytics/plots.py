"""Figures for the responder analysis.

Three figures, all deterministic so the report regenerates identically:
  responder_boxplot          five panels of baseline frequency by response, with
                             seeded jittered subject points
  responder_trajectory_plot  five panels of mean frequency over time, one line
                             per response group, showing where the groups diverge
  effect_size_forest_plot    the rank-biserial effect size per population with a
                             bootstrap confidence interval
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import matplotlib

matplotlib.use("Agg")  # no interactive display in library code

import matplotlib.pyplot as plt  # noqa: E402  (backend must be set first)
import numpy as np  # noqa: E402

from . import CELL_POPULATIONS  # noqa: E402
from .stats import (  # noqa: E402
    DEFAULT_DB,
    Unit,
    bootstrap_effect_ci,
    cohort_frequencies,
    compare_responders,
    trajectory_summary,
)

# The two response groups, in the order they appear on every panel.
_GROUPS = ("yes", "no")
_GROUP_LABELS = ("Responder", "Non-responder")

# Jitter width around each group's x position, and the seed that fixes it.
_JITTER_WIDTH = 0.08
_JITTER_SEED = 0

_FIG_WIDTH = 16.0
_FIG_HEIGHT = 4.0
_DPI = 150

# A colour per response group so the trajectory lines read the same everywhere.
_GROUP_COLORS = {"yes": "#1f77b4", "no": "#d62728"}

# Bootstrap resamples for the forest plot confidence intervals, and its seed.
_FOREST_N_BOOT = 2000
_FOREST_SEED = 0
_FOREST_WIDTH = 9.0
_FOREST_HEIGHT = 4.0


def responder_boxplot(
    db_path: Path = DEFAULT_DB,
    out_path: Path = DEFAULT_DB.parent / "outputs" / "responder_boxplot.png",
    unit: Unit = "baseline",
) -> Path:
    """Draw the faceted responder boxplot and save it to out_path.

    Each of the five panels shows one population's relative frequency for
    responders and non-responders, with jittered subject points overlaid. The
    parent directory is created if needed. Returns the saved path.
    """
    freq = cohort_frequencies(db_path, unit)
    rng = np.random.default_rng(_JITTER_SEED)

    fig, axes = plt.subplots(1, len(CELL_POPULATIONS), figsize=(_FIG_WIDTH, _FIG_HEIGHT))

    for ax, population in zip(axes, CELL_POPULATIONS, strict=True):
        sub = freq.loc[freq["population"] == population]
        values = [sub.loc[sub["response"] == group, "percentage"].to_numpy() for group in _GROUPS]

        ax.boxplot(values, tick_labels=_GROUP_LABELS, showfliers=False)
        for position, group_values in enumerate(values, start=1):
            jitter = rng.uniform(-_JITTER_WIDTH, _JITTER_WIDTH, size=len(group_values))
            ax.scatter(position + jitter, group_values, s=8, alpha=0.4, color="#1f77b4")

        ax.set_title(population)
        ax.set_ylabel("Relative frequency (%)")

    unit_label = "baseline" if unit == "baseline" else "subject mean"
    fig.suptitle(
        f"Immune cell population frequency by treatment response ({unit_label}), "
        f"melanoma miraclib PBMC"
    )
    fig.tight_layout()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=_DPI)
    plt.close(fig)
    return out_path


def responder_trajectory_plot(
    db_path: Path = DEFAULT_DB,
    out_path: Path = DEFAULT_DB.parent / "outputs" / "responder_trajectory.png",
) -> Path:
    """Draw the mean frequency over time by response group and save it.

    Each of the five panels shows one population. Within a panel the mean
    relative frequency is plotted at each timepoint for responders and for
    non-responders, with 95 percent confidence interval error bars. This makes
    plain where the two groups track together and where they diverge. The parent
    directory is created if needed. Returns the saved path.
    """
    summary = trajectory_summary(db_path)

    fig, axes = plt.subplots(1, len(CELL_POPULATIONS), figsize=(_FIG_WIDTH, _FIG_HEIGHT))

    for ax, population in zip(axes, CELL_POPULATIONS, strict=True):
        panel = summary.loc[summary["population"] == population]
        for group, label in zip(_GROUPS, _GROUP_LABELS, strict=True):
            line = panel.loc[panel["response"] == group].sort_values("timepoint")
            ax.errorbar(
                line["timepoint"],
                line["mean"],
                yerr=line["ci_half"],
                marker="o",
                capsize=3,
                label=label,
                color=_GROUP_COLORS[group],
            )
        ax.set_title(population)
        ax.set_xlabel("Days from treatment start")
        ax.set_ylabel("Relative frequency (%)")
        ax.set_xticks(sorted(panel["timepoint"].unique()))

    axes[0].legend()
    fig.suptitle(
        "Immune cell population frequency over time by treatment response "
        "(mean with 95% CI), melanoma miraclib PBMC"
    )
    fig.tight_layout()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=_DPI)
    plt.close(fig)
    return out_path


def effect_size_forest_plot(
    db_path: Path = DEFAULT_DB,
    out_path: Path = DEFAULT_DB.parent / "outputs" / "responder_effect_forest.png",
    unit: Unit = "baseline",
) -> Path:
    """Draw a forest plot of the per-population effect size and save it.

    For each population the rank-biserial effect size from compare_responders is
    plotted as a point with a horizontal bootstrap 95 percent confidence interval
    bar, against a vertical reference line at zero. A positive value means
    responders tend to be higher. Populations are shown in the canonical order,
    first at the top. The title states the unit of analysis. The parent directory
    is created if needed. Returns the saved path.
    """
    results = compare_responders(db_path, unit).set_index("population")
    freq = cohort_frequencies(db_path, unit)

    fig, ax = plt.subplots(figsize=(_FOREST_WIDTH, _FOREST_HEIGHT))

    positions = list(range(len(CELL_POPULATIONS)))
    for position, population in zip(positions, CELL_POPULATIONS, strict=True):
        sub = freq.loc[freq["population"] == population]
        yes = sub.loc[sub["response"] == "yes", "percentage"].to_numpy()
        no = sub.loc[sub["response"] == "no", "percentage"].to_numpy()
        point = cast(float, results.loc[population, "effect_size"])
        low, high = bootstrap_effect_ci(yes, no, n_boot=_FOREST_N_BOOT, seed=_FOREST_SEED)
        ax.errorbar(
            point,
            position,
            xerr=[[point - low], [high - point]],
            fmt="o",
            capsize=4,
            color="#1f77b4",
        )

    ax.axvline(0.0, color="grey", linestyle="--", linewidth=1)
    ax.set_yticks(positions)
    ax.set_yticklabels(list(CELL_POPULATIONS))
    ax.invert_yaxis()
    ax.set_xlabel("Rank-biserial effect size (positive means higher in responders)")

    unit_label = "baseline" if unit == "baseline" else "subject mean"
    ax.set_title(
        f"Responder effect size by population with bootstrap 95% CI ({unit_label}), "
        f"melanoma miraclib PBMC"
    )
    fig.tight_layout()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=_DPI)
    plt.close(fig)
    return out_path
