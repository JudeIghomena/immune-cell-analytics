"""Interactive dashboard for the immune cell analytics project.

Run it from the repository root with:

    streamlit run app.py

This script is the presentation layer only. Every query lives in the package
(dashboard_data, stats, subsets) and every figure in plots, so the logic is
tested there and this file stays thin. Nothing here is imported by the tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from immune_cell_analytics import plots, stats
from immune_cell_analytics.dashboard_data import (
    DEFAULT_DB,
    frequency_with_metadata,
    sample_metadata,
)

# The sidebar cohort filters, their column names, and their default values.
_FILTERS = ("condition", "treatment", "sample_type", "timepoint")
_FILTER_LABELS = {
    "condition": "Condition",
    "treatment": "Treatment",
    "sample_type": "Sample type",
    "timepoint": "Timepoint",
}
_DEFAULTS: dict[str, object] = {
    "condition": "melanoma",
    "treatment": "miraclib",
    "sample_type": "PBMC",
    "timepoint": 0,
}
_ALL = "All"

# The two units of analysis offered by the responder toggle.
_UNIT_BY_LABEL = {
    "Baseline (primary)": "baseline",
    "Per-subject mean (sensitivity)": "subject_mean",
}


@st.cache_data
def load_frequency(db_path: Path) -> pd.DataFrame:
    """Load the frequency-with-metadata frame, cached by database path."""
    return frequency_with_metadata(db_path)


@st.cache_data
def load_metadata(db_path: Path) -> pd.DataFrame:
    """Load the per-sample metadata frame, cached by database path."""
    return sample_metadata(db_path)


def apply_cohort(df: pd.DataFrame, selections: dict[str, object]) -> pd.DataFrame:
    """Return the rows of df that match every non-All selection."""
    mask = pd.Series(True, index=df.index)
    for column, value in selections.items():
        if value != _ALL:
            mask &= df[column] == value
    return df[mask]


def sidebar_selections(meta: pd.DataFrame) -> dict[str, object]:
    """Draw the sidebar filters and return the current selection per column.

    Each filter is a selectbox with an All option plus the distinct values from
    the data. A reset button clears the filters back to their defaults.
    """
    st.sidebar.header("Cohort filters", divider="gray")

    if st.sidebar.button("Reset filters", icon=":material/refresh:", width="stretch"):
        for column in _FILTERS:
            st.session_state.pop(column, None)

    selections: dict[str, object] = {}
    for column in _FILTERS:
        options: list[object] = [_ALL, *sorted(meta[column].unique())]
        # Fall back to the first option if a default value is absent from the data,
        # so the app never crashes on a differently shaped database.
        default = _DEFAULTS[column]
        default_index = options.index(default) if default in options else 0
        selections[column] = st.sidebar.selectbox(
            _FILTER_LABELS[column], options, index=default_index, key=column
        )
    return selections


def show_cohort_summary(selections: dict[str, object], n_samples: int) -> None:
    """Show the live cohort and the number of samples it selects."""
    st.sidebar.subheader("Current cohort", divider="gray")
    st.sidebar.metric("Samples in cohort", n_samples)
    parts = [f"{_FILTER_LABELS[column]}: {selections[column]}" for column in _FILTERS]
    st.sidebar.caption(" · ".join(parts))


def render_overview(freq: pd.DataFrame, selections: dict[str, object]) -> None:
    """Data overview tab: the cohort frequency table with a sample search."""
    st.subheader("Data overview", icon=":material/table_chart:")
    st.caption("Relative frequency of each population, filtered by the sidebar cohort.")
    filtered = apply_cohort(freq, selections)

    search = st.text_input("Search sample id", "", placeholder="Type part of a sample id")
    if search:
        filtered = filtered[filtered["sample"].str.contains(search, case=False, na=False)]

    table = filtered[["sample", "total_count", "population", "count", "percentage"]].copy()
    table["percentage"] = table["percentage"].round(2)

    with st.container(border=True):
        st.dataframe(table, width="stretch", hide_index=True)
        st.caption(f"{len(table)} rows")


def render_responders(db_path: Path) -> None:
    """Responder analysis tab: fixed clinical cohort stats and figures."""
    st.subheader("Responder analysis", icon=":material/biotech:")
    st.caption(
        "This tab is fixed to the clinical cohort melanoma, miraclib, PBMC, "
        "independent of the sidebar, because responders only exist for treated "
        "cohorts."
    )

    label = st.segmented_control(
        "Unit of analysis",
        list(_UNIT_BY_LABEL),
        default=next(iter(_UNIT_BY_LABEL)),
    )
    if label is None:
        label = next(iter(_UNIT_BY_LABEL))
    unit = _UNIT_BY_LABEL[label]

    results = stats.compare_responders(db_path, unit)
    with st.container(border=True):
        st.markdown("Responder comparison")
        st.dataframe(results, width="stretch", hide_index=True)
        st.write(stats.conclusion(results, unit))

    st.subheader("Figures", icon=":material/insights:")
    st.caption("Figures are computed on the baseline unit.")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        boxplot = plots.responder_boxplot(db_path, tmp_path / "boxplot.png", unit="baseline")
        trajectory = plots.responder_trajectory_plot(db_path, tmp_path / "trajectory.png")
        forest = plots.effect_size_forest_plot(db_path, tmp_path / "forest.png", unit="baseline")

        with st.container(border=True):
            st.image(str(boxplot), width="stretch")
            st.caption("Population frequency by response group.")
        with st.container(border=True):
            st.image(str(trajectory), width="stretch")
            st.caption("Population frequency trajectory over time.")
        with st.container(border=True):
            st.image(str(forest), width="stretch")
            st.caption("Effect size per population with confidence intervals.")


def render_subset(meta: pd.DataFrame, selections: dict[str, object]) -> None:
    """Subset explorer tab: metric cards and breakdown bar charts."""
    st.subheader("Subset explorer", icon=":material/groups:")
    st.caption("Cohort composition for the current sidebar filters.")
    filtered = apply_cohort(meta, selections)

    n_samples = len(filtered)
    n_subjects = filtered["subject"].nunique()
    responders = filtered.loc[filtered["response"] == "yes", "subject"].nunique()
    non_responders = filtered.loc[filtered["response"] == "no", "subject"].nunique()
    male = filtered.loc[filtered["sex"] == "M", "subject"].nunique()
    female = filtered.loc[filtered["sex"] == "F", "subject"].nunique()

    row1 = st.columns(2)
    row1[0].metric("Samples", n_samples, border=True)
    row1[1].metric("Distinct subjects", n_subjects, border=True)

    row2 = st.columns(4)
    row2[0].metric("Responders", responders, border=True)
    row2[1].metric("Non-responders", non_responders, border=True)
    row2[2].metric("Male", male, border=True)
    row2[3].metric("Female", female, border=True)

    if filtered.empty:
        st.info("No samples match the current cohort.", icon=":material/info:")
        return

    with st.container(border=True):
        st.markdown("Samples per project")
        st.bar_chart(filtered.groupby("project").size(), width="stretch")

    charts = st.columns(2)
    with charts[0].container(border=True, height="stretch"):
        st.markdown("Distinct subjects by response")
        st.bar_chart(filtered.groupby("response")["subject"].nunique(), width="stretch")
    with charts[1].container(border=True, height="stretch"):
        st.markdown("Distinct subjects by sex")
        st.bar_chart(filtered.groupby("sex")["subject"].nunique(), width="stretch")


def main() -> None:
    st.set_page_config(
        page_title="Immune cell analytics",
        page_icon=":material/science:",
        layout="wide",
    )
    st.title("Immune cell analytics", icon=":material/science:")
    st.caption("Cell population frequencies and responder analysis across the study cohort.")

    db_path = DEFAULT_DB
    if not db_path.exists():
        st.error(
            "Database not found. Run python load_data.py first to build cell_count.db.",
            icon=":material/error:",
        )
        st.stop()

    freq = load_frequency(db_path)
    meta = load_metadata(db_path)

    selections = sidebar_selections(meta)
    show_cohort_summary(selections, len(apply_cohort(meta, selections)))

    overview_tab, responder_tab, subset_tab = st.tabs(
        [
            ":material/table_chart: Data overview",
            ":material/biotech: Responder analysis",
            ":material/groups: Subset explorer",
        ]
    )
    with overview_tab:
        render_overview(freq, selections)
    with responder_tab:
        render_responders(db_path)
    with subset_tab:
        render_subset(meta, selections)


main()
