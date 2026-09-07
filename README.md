# Immune Cell Analytics

This project looks at immune cell counts from a clinical trial of miraclib in
melanoma and works out whether the makeup of a patient's immune cells says
anything about who responds to the drug. It starts from one file of blood
samples, loads it into a normalized SQLite database, turns the raw cell counts
into relative frequencies, tests responders against non-responders, describes a
baseline cohort, and puts all of it behind an interactive dashboard.

The data is a single file, cell-count.csv, with 10,500 samples. Every sample
carries raw integer counts for five immune cell populations, b_cell, cd8_t_cell,
cd4_t_cell, nk_cell, and monocyte, plus some metadata about the subject and the
sample. I delivered the work in four parts, with a dashboard on top:

1. Data management: the schema and the loader.
2. Relative frequency: each population as a percent of its sample total.
3. Statistical analysis: responders versus non-responders on miraclib.
4. Subset analysis: a baseline melanoma miraclib PBMC cohort, described.

This README is the map. If you want the reasoning behind each decision and the
honest conclusions, that lives in Report.md, where I wrote up my thinking part
by part.

## How to run and reproduce

I built this to run in GitHub Codespaces with three Makefile targets, so you can
go from a fresh checkout to a running dashboard without much ceremony. You need
Python 3.10 or newer. Run the three targets in order, and each one sets up the
next.

Start by installing the dependencies:

```bash
make setup
```

That upgrades pip and installs the package in editable mode with its analysis
and dashboard extras, all declared in pyproject.toml. The analysis extra brings
in matplotlib and scipy, and the dashboard extra brings in streamlit.

Then build the database and regenerate every output:

```bash
make pipeline
```

This runs four steps in order, and it is safe to re-run because the loader
rebuilds a clean database from the CSV each time. First `python load_data.py`
builds cell_count.db in the repository root and loads every row, 3 projects,
3,500 subjects, 3,500 treatment episodes, 10,500 samples, and 52,500
measurements. Then `python -m immune_cell_analytics.analysis` writes the Part 2
relative frequency table, `python -m immune_cell_analytics.stats` writes the
Part 3 statistics tables and figures, and `python -m immune_cell_analytics.subsets`
writes the Part 4 subset tables.

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

Finally, launch the dashboard:

```bash
make dashboard
```

This starts Streamlit at http://localhost:8501. In Codespaces the port is
forwarded automatically, so open the forwarded URL when the terminal prints it.
Run make pipeline at least once first, so the database exists. If it does not,
the dashboard shows a clear message asking you to run the loader rather than
failing on you.

If you want to check the work, the test suite is an optional extra:

```bash
pip install -e ".[analysis,dashboard,dev]"
pytest
```

The suite covers the loader, the schema integrity, the relative frequency table,
the statistics, the plots, the subset counts, and the dashboard data helpers.

## Database schema

I did not load the CSV as one flat table. The loader pulls it apart into five
tables plus one view, so that each fact is stored exactly once and nothing has
to be repeated across rows.

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
this dataset, so the relationship is one to one here, but I modeled it as one to
many so a subject could later carry more than one episode without a redesign. An
episode holds many samples, one per timepoint, and each sample holds five
measurements, one per population, stored in long format.

The view sample_population_frequency is the single source of truth for relative
frequency. It computes, per sample, the total across the five populations and
each population as a percent of that total, using a window function.

### Rationale

Each fact lives in one place. In the raw CSV every subject attribute is repeated
across that subject's three sample rows, and repeated facts drift out of sync
over time and force every query to work around the duplication. Collapsing the
constant attributes onto subject removes that risk. I checked the constancy
against the data before fixing the design, and there were zero violations.

Response belongs to the treatment episode, not the sample. Response is the
outcome of a course of treatment, so I put it on treatment_episode. Once it
lives there, the blank response for an untreated or healthy subject stops
looking like missing data and becomes structurally correct: there was no
treatment, so there is no outcome. A CHECK constraint ties the two together, so
the database refuses a treated episode with no outcome or an untreated episode
that claims one.

The five counts are stored long, five rows per sample rather than five columns.
This makes the relative frequency summary a single grouped query instead of five
repeated column references, and it means a future sixth population is a new row,
not a schema change that ripples through every query. A CHECK constraint pins the
population name to the five expected values, so the openness never lets a typo
in, and the extra rows cost nothing at this size.

Every table has a surrogate key and a unique natural code. There is a stable
integer primary key for joins and a UNIQUE constraint on the real-world code
(project_code, subject_code, sample_code), so a genuine duplicate is rejected
outright.

I let the database enforce the real invariants rather than trusting the loader.
condition, sex, treatment, and sample_type are constrained to their known value
sets, counts cannot be negative, age is bounded, and the response-to-treatment
rule described above is enforced in the database itself.

The view is the one definition of relative frequency. It is defined once and read
by both Part 2 and the dashboard, so the number a reader sees in the file is
always the same number the dashboard shows. The percentage is stored at full
precision and rounded only where a human reads it, so per-sample percentages sum
to exactly one hundred.

### How this scales

The dataset here is small, but I designed for growth to hundreds of projects and
thousands to millions of samples without a rewrite.

I indexed only the real paths, the columns the analysis actually filters and
joins on: subject by project and by condition, episode by subject and by
response, sample by episode, and sample by the sample_type and timepoint pair. I
did not add an index on a hunch, because an index nothing uses is pure cost.

From there the plan is staged by scale:

- Today, at small scale, the normalized tables plus the targeted indexes above
  are enough, and cohort queries are fast filtered joins.
- At millions of rows, materialize the frequency view into a table refreshed by
  the loader and add covering indexes for the hottest cohort filters, so the
  per-sample window computation is paid once rather than on every read.
- At tens of millions of rows, partition the measurement table by project or by
  time, so a cohort query touches only the relevant partitions.

The schema also evolves without migration. Because measurements are long, a new
cell population is new rows and a widened CHECK, not an ALTER that touches every
query. New per-sample or per-subject metadata is a new column on the table that
owns that grain, leaving the rest untouched.

SQLite is the right fit for a single-analyst, single-file deliverable. When the
workload needs concurrent writers, database roles with least privilege, or
heavier analytical queries, the same normalized schema moves to PostgreSQL with
minimal change and gains materialized views, partitioning, and richer indexing.
And any new cohort question stays simple, because it is a filtered join and
aggregation over the same normalized core. Where a question gets asked often, it
becomes an extra view or a small rollup table, without disturbing the core
tables or the queries that already exist.

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

load_data.py sits at the repository root and I kept it deliberately
self-contained. It depends only on pandas and the standard library, so it runs
without installing the project package, which matters for portable grading. It
is idempotent, so each run rebuilds a clean database from the CSV. It inserts
through parameterized statements in one transaction with foreign keys on, and it
validates the input first, stopping with a clear message on a duplicated sample,
a subject with two treatments, or a subject whose attributes disagree across
rows, rather than loading a database that is subtly wrong.

The package src/immune_cell_analytics/ holds the analysis, one responsibility per
module. __init__.py holds the shared constants and the single COHORT_WHERE
fragment that defines the clinical cohort. analysis.py builds the Part 2 relative
frequency table from the view. stats.py runs the Part 3 Mann-Whitney U tests with
Benjamini-Hochberg correction and effect sizes. plots.py draws the Part 3
figures. subsets.py runs the Part 4 cohort counts. dashboard_data.py is the
tested data-access layer the dashboard reads through.

app.py is a thin presentation layer at the root. It reuses the tested helpers in
the package rather than recomputing anything, so all of the logic stays under
test while the app stays a display concern.

The thread running through all of this is a single source of truth for each
computed thing. Relative frequency is defined once in the SQL view, and the
cohort is defined once in COHORT_WHERE. Presentation stays thin so the logic
stays tested, the loader stays self-contained so grading stays portable, and the
modules stay small and single-purpose so each one is easy to read and to test on
its own.

## The dashboard

The dashboard is served on demand, not hosted somewhere separately. There is no
standalone URL to visit. You run make dashboard and it starts locally at
http://localhost:8501, and in Codespaces the port is forwarded automatically, so
you open the forwarded URL. It has three tabs: a data overview (Part 2), a
responder analysis (Part 3), and a subset explorer (Part 4). Sidebar cohort
filters drive the overview and the subset explorer live. The responder analysis
stays fixed to the clinical cohort of melanoma, miraclib, and PBMC samples,
because response only exists for treated subjects and that fixed comparison is
the scientifically valid question.

## A note on column names

One thing worth flagging early, because it saves confusion later: the task
write-up and the actual data file use different names for three columns. I kept
the real file names and modeled the extra columns the brief does not mention.

| Name in the brief | Name in the file |
|---|---|
| sample_id | sample |
| indication | condition |
| gender | sex |

The other named columns (treatment, response, time_from_treatment_start) line
up. The file also carries project, subject, age, and sample_type, which the
brief does not name, and I kept and modeled all four. Subject matters the most,
because it identifies the repeated samples from one person, and the statistical
analysis depends on that to avoid treating three samples from one subject as
three independent observations.

There is also one output column named count, which happens to be a SQL keyword.
I kept the name because the specification asks for that exact name and SQLite
handles it correctly, and I am flagging it here so it reads as a deliberate
choice rather than an oversight.
