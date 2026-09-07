# Immune Cell Analytics

This project analyzes immune cell population counts from a clinical trial of
miraclib in melanoma. It takes one dataset of blood samples, loads it into a
normalized SQLite database, converts raw cell counts into relative frequencies,
tests whether immune composition separates treatment responders from
non-responders, describes a baseline cohort, and serves all of it through an
interactive dashboard.

The dataset is a single file, cell-count.csv, with 10,500 samples. Each sample
carries raw integer counts for five immune cell populations, b_cell, cd8_t_cell,
cd4_t_cell, nk_cell, and monocyte, plus metadata about the subject and the
sample. The analysis is delivered in four parts plus the dashboard:

1. Data management: the schema and the loader.
2. Relative frequency: each population as a percent of its sample total.
3. Statistical analysis: responders versus non-responders on miraclib.
4. Subset analysis: a baseline melanoma miraclib PBMC cohort, described.

The full analytical narrative, with the reasoning behind each decision and the
honest conclusions, lives in Report.md.

## How to run and reproduce

The project is built to run in GitHub Codespaces using three Makefile targets.
Python 3.10 or newer is required. Run the targets in order.

### 1. Install dependencies

```bash
make setup
```

This upgrades pip and installs the package in editable mode with its analysis
and dashboard extras, all declared in pyproject.toml. The analysis extra pulls
in matplotlib and scipy, and the dashboard extra pulls in streamlit.

### 2. Build the database and regenerate every output

```bash
make pipeline
```

This runs four steps in order and is safe to re-run, since the loader rebuilds a
clean database each time:

1. `python load_data.py` builds cell_count.db in the repository root and loads
   every row (3 projects, 3,500 subjects, 3,500 treatment episodes, 10,500
   samples, 52,500 measurements).
2. `python -m immune_cell_analytics.analysis` writes the Part 2 relative
   frequency table.
3. `python -m immune_cell_analytics.stats` writes the Part 3 statistics tables
   and figures.
4. `python -m immune_cell_analytics.subsets` writes the Part 4 subset tables.

Everything lands in outputs/:

| File | What it holds |
|---|---|
| relative_frequencies.csv | Part 2. One row per population per sample (52,500 rows): sample, total_count, population, count, percentage. |
| responder_stats_baseline.csv | Part 3 primary analysis. Per-population group sizes, medians, U, raw and adjusted p-values, effect size. |
| responder_stats_subject_mean.csv | Part 3 sensitivity analysis, per subject mean across timepoints. |
| responder_boxplot.png | Part 3. Distribution of each population by response group. |
| responder_effect_forest.png | Part 3. Effect size per population with a bootstrapped confidence interval. |
| responder_trajectory.png | Part 3. Mean relative frequency over days 0, 7, 14 by response group. |
| subset_samples.csv | Part 4. The baseline melanoma miraclib PBMC cohort. |
| subset_by_project.csv | Part 4. Sample counts by project. |
| subset_by_response.csv | Part 4. Subject counts by response. |
| subset_by_sex.csv | Part 4. Subject counts by sex. |

### 3. Launch the dashboard

```bash
make dashboard
```

This starts Streamlit at http://localhost:8501. In Codespaces the port is
forwarded automatically, so open the forwarded URL when the terminal prints it.
Run make pipeline at least once first, so the database exists. If it does not,
the dashboard shows a clear message asking you to run the loader.

### Optional: run the test suite

```bash
pip install -e ".[analysis,dashboard,dev]"
pytest
```

The suite covers the loader, the schema integrity, the relative frequency table,
the statistics, the plots, the subset counts, and the dashboard data helpers.

## Database schema

The loader decomposes the flat CSV into five tables plus one view. The design is
normalized so that each fact is stored exactly once.

### Tables and relationships

```
project ──1:N── subject ──1:1── treatment_episode ──1:N── sample ──1:N── measurement
```

| Table | Grain | Key columns |
|---|---|---|
| project | one study | project_id, project_code |
| subject | one person | subject_id, subject_code, project_id, condition, sex, age |
| treatment_episode | one course of treatment | episode_id, subject_id, treatment, response |
| sample | one specimen at one timepoint | sample_id, sample_code, episode_id, sample_type, time_from_treatment_start |
| measurement | one population count in one sample | sample_id, population, count |

A project holds many subjects. Each subject has exactly one treatment episode in
this dataset, so the relationship is one to one here, though the schema models it
as one to many so a subject could later carry more than one episode without a
redesign. An episode holds many samples, one per timepoint. Each sample holds
five measurements, one per population, stored in long format.

The view sample_population_frequency is the single source of truth for relative
frequency. It computes, per sample, the total across the five populations and
each population as a percent of that total, using a window function.

### Rationale

Normalization so each fact lives once. In the raw CSV every subject attribute is
repeated across that subject's three sample rows. Repeated facts drift out of
sync over time and force every query to work around the duplication. Collapsing
the constant attributes onto subject removes that risk. The constancy was
verified against the data before the design was fixed, with zero violations.

Response modeled on the treatment episode. Response is the outcome of a course of
treatment, not a property of a specimen, so it lives on treatment_episode. Once
it lives there, the blank response for an untreated or healthy subject stops
looking like missing data and becomes structurally correct: there was no
treatment, so there is no outcome. A CHECK constraint ties the two together, so
the database refuses a treated episode with no outcome or an untreated episode
that claims one.

Long-format measurements. The five counts are stored as five rows per sample
rather than five columns. This makes the relative frequency summary a single
grouped query rather than five repeated column references, and it means a future
sixth population is a new row, not a schema change that ripples through every
query. A CHECK constraint pins the population name to the five expected values,
so the openness never lets a typo in. The extra rows cost nothing at this size.

Surrogate keys plus unique natural codes. Every table has a stable integer
primary key for joins and a UNIQUE constraint on its real-world code
(project_code, subject_code, sample_code), so a genuine duplicate is rejected
outright.

CHECK constraints on real invariants. condition, sex, treatment, and sample_type
are constrained to their known value sets, counts cannot be negative, age is
bounded, and the response-to-treatment rule described above is enforced in the
database, not left to the loader.

The view as one definition. Relative frequency is defined once in the view and
read by Part 2 and the dashboard, so the number a reader sees in the file is
always the same number the dashboard shows. The percentage is stored at full
precision and rounded only where a human reads it, so per-sample percentages sum
to exactly one hundred.

### How this scales

The dataset here is small, but the design is built to grow to hundreds of
projects and thousands to millions of samples without a rewrite.

Indexes on the real paths. Indexes exist only on the columns the analysis
actually filters and joins on: subject by project and by condition, episode by
subject and by response, sample by episode, and sample by the sample_type and
timepoint pair. No index was added on a hunch, because an index nothing uses is
pure cost.

A staged plan by scale:

- Small scale (today): the normalized tables plus the targeted indexes above are
  enough. Cohort queries are fast filtered joins.
- Millions of rows: materialize the frequency view into a table refreshed by the
  loader, and add covering indexes for the hottest cohort filters, so the
  per-sample window computation is paid once rather than on every read.
- Tens of millions of rows: partition the measurement table by project or by
  time, so a cohort query touches only the relevant partitions.

Schema evolution without migration. Because measurements are long, a new cell
population is new rows and a widened CHECK, not an ALTER across every query. New
per-sample or per-subject metadata is a new column on the table that owns that
grain, leaving the rest untouched.

Moving off SQLite when needed. SQLite is the right fit for a single-analyst,
single-file deliverable. When the workload needs concurrent writers, database
roles with least privilege, or heavier analytical queries, the same normalized
schema moves to PostgreSQL with minimal change, gaining materialized views,
partitioning, and richer indexing.

Arbitrary analytics stay simple. Any new cohort question is a filtered join and
aggregation over the same normalized core. Where a question is asked often, it
becomes an extra view or a small rollup table, without disturbing the core
tables or the existing queries.

## Code structure

```
load_data.py                          self-contained loader (root)
app.py                                thin Streamlit dashboard (root)
src/immune_cell_analytics/
    __init__.py                       constants and the shared COHORT_WHERE
    analysis.py                       Part 2, relative frequency
    stats.py                          Part 3, statistics
    plots.py                          Part 3, figures
    subsets.py                        Part 4, cohort counts
    dashboard_data.py                 data access for the dashboard
tests/                               pytest suite
outputs/                             generated CSVs and figures
Report.md                            the analytical narrative
```

load_data.py lives at the repository root and is deliberately self-contained. It
depends only on pandas and the standard library, so it runs without installing
the project package, which matters for portable grading. It is idempotent, so
each run rebuilds a clean database from the CSV. It inserts through parameterized
statements in one transaction with foreign keys on, and it validates the input
first, stopping with a clear message on a duplicated sample, a subject with two
treatments, or a subject whose attributes disagree across rows, rather than
loading a database that is subtly wrong.

The package src/immune_cell_analytics/ holds the analysis, one responsibility per
module. __init__.py holds shared constants and the single COHORT_WHERE fragment
that defines the clinical cohort. analysis.py builds the Part 2 relative
frequency table from the view. stats.py
runs the Part 3 Mann-Whitney U tests with Benjamini-Hochberg correction and
effect sizes. plots.py draws the Part 3 figures. subsets.py runs the Part 4
cohort counts. dashboard_data.py is the tested data-access layer the dashboard
reads through.

app.py is a thin presentation layer at the root. It reuses the tested helpers in
the package rather than recomputing anything, so all of the logic stays under
test while the app stays a display concern.

Rationale. There is a single source of truth for each computed thing: relative
frequency is defined once in the SQL view, and the cohort is defined once in
COHORT_WHERE. Presentation is kept thin so that logic stays tested. The loader is
self-contained so grading is portable. The modules are small and single-purpose
so each is easy to read and to test on its own.

## The dashboard

The dashboard is served on demand, not hosted separately. Run make dashboard and
it starts locally at http://localhost:8501. In Codespaces the port is forwarded
automatically, so open the forwarded URL. It has three tabs: a data overview
(Part 2), a responder analysis (Part 3), and a subset explorer (Part 4). Sidebar
cohort filters drive the overview and the subset explorer live. The responder
analysis stays fixed to the clinical cohort of melanoma, miraclib, and PBMC
samples, because response only exists for treated subjects and that fixed
comparison is the scientifically valid question.

## Note on column names

The task write-up and the actual data file use different names for three
columns. This project keeps the real file names and models the extra columns the
brief does not mention.

| Name in the brief | Name in the file |
|---|---|
| sample_id | sample |
| indication | condition |
| gender | sex |

The other named columns (treatment, response, time_from_treatment_start) match.
The file also carries project, subject, age, and sample_type, which the brief
does not name. All four were kept and modeled. Subject matters most: it
identifies the repeated samples from one person, which the statistical analysis
depends on to avoid treating three samples from one subject as three independent
observations.

One output column is named count, which is also a SQL keyword. It is kept because
the specification asks for that exact name, and SQLite handles it correctly. It
is flagged here so it reads as a deliberate choice.
</content>
</invoke>
