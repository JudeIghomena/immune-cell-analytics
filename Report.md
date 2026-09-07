# Immune Cell Analytics Report

This report explains the reasoning behind the immune cell count analysis for
Loblaw Bio, part by part. The project starts from one file of blood samples,
loads it into a normalized SQLite database, converts raw cell counts into
relative frequencies, tests responders against non-responders on miraclib,
describes a baseline cohort, and puts all of it behind an interactive dashboard.

The headline finding is a careful negative. Once the statistics are done
properly, no immune cell population separates responders from non-responders in
this cohort. There is one on-treatment lead worth noting, CD4 T cells rising in
responders, but it does not survive a fair correction for multiple testing, so I
report it as a candidate for a larger study rather than a result to act on. The
sections below give the data model, the normalization, the statistical method,
the subset description, and the dashboard, with the reasoning under each so a
reviewer can follow every decision.

The source is a single file, cell-count.csv, with 10,500 blood samples. Each
sample carries five immune cell population counts, b_cell, cd8_t_cell,
cd4_t_cell, nk_cell, and monocyte, along with metadata about the subject and the
sample.

One item is worth flagging early, because it saves confusion later. The task
write-up and the actual file use different names for three columns. In the file,
the specimen id is sample, which the brief calls sample_id. The disease is
condition, which the brief calls indication. Sex is sex, which the brief calls
gender. The remaining named columns line up. The file also carries columns the
brief never mentions: project, subject, age, and sample_type. I kept and modeled
all four. Subject matters the most, because it identifies which samples came from
the same person, and the statistical analysis is not honest without it.

## Part 1: Data management

The deliverable for Part 1 is a SQLite database that models the data well and a
load_data.py that builds it and loads every row. The modeling was the substance
of the work, so that is what this section walks through.

I did not load the CSV as one flat table. Each subject gives three samples, and
on all three rows the subject's condition, sex, age, treatment, and response are
repeated. When the same fact is written down repeatedly, two copies eventually
disagree, and every query has to work around the duplication. That repetition was
the signal to pull the file apart into separate things that each own their own
facts.

I checked the shape of the data before committing to any structure, because a
model built on a guess breaks the first time reality disagrees. Three checks came
back clean. Every attribute of a subject is identical across that subject's
samples, with no exceptions, so those attributes are safe to store once on the
subject. Every subject has exactly one treatment, so a single course of treatment
per subject is the right unit. Response is filled in for treated subjects and
blank for the healthy and untreated ones, with nothing in between, so that blank
carries meaning rather than being a hole in the data. Because these held
perfectly, the design rests on facts rather than hope.

The result is five connected pieces. A project holds many subjects. A subject
belongs to a project and has one course of treatment. That course of treatment
holds the subject's samples over time. Each sample holds its five cell
measurements. Read the other way, a measurement belongs to a sample, a sample to
a treatment course, a course to a subject, and a subject to a project. It is a
clean chain with nothing pointing back on itself, which keeps every query and
every load straightforward.

The decision I am most confident about is where response lives. In the raw file
it sits on the sample row and is blank for anyone untreated, which looks like
missing data and invites people to patch or drop it. It is not missing. Response
is the outcome of a course of treatment, so I attached it to the treatment
record, not the sample. Once it lives there, the blank for an untreated subject
stops being a problem to explain and becomes simply correct: there was no
treatment, so there is no outcome. That move also removes a column whose blank
would otherwise have meant two different things at once.

On the five cell counts I had a choice between five columns side by side and one
row per population. I chose one row per population. It makes the relative
frequency summary a single clean query instead of five repeated column
references, and if a future panel adds a sixth cell type, that is more rows
rather than a change to the tables and every query that touches them. The only
cost is a few more rows in one table, which is nothing at this size, so the
flexibility is essentially free. I added a guard so the population name can only
be one of the five expected values, so the openness never turns into a typo
sneaking in.

A vector database does not belong here. That tool finds things similar in meaning
across unstructured data. Every question in this project is an exact filter,
join, or count over structured numbers, which is what a relational database is
built for. I do use fast vectorized pandas operations inside the loader, but that
is a different idea and not the same thing.

I leaned on the database to keep itself honest rather than trusting the loader to
always be careful. Every table has a stable internal key and a unique constraint
on its real-world code, so a genuine duplicate is rejected outright. The tables
are linked so an orphan record cannot exist. Values are constrained to the
expected sets, counts cannot go negative, and a rule ties response to treatment,
so the database refuses a row that claims an outcome with no treatment or a
treatment with no outcome. I also added a view that returns each population as a
percentage of its sample, computed once and safe against an empty sample, so the
later parts read from one agreed definition instead of each recomputing it.

I indexed only what the later questions actually filter and join on: condition,
response, sample type and timepoint, and the links between tables. I did not add
indexes on a hunch, because an index nothing uses is pure cost.

The loader sits in the root and runs with a plain python load_data.py, no
arguments. It builds cell_count.db in the root, loads everything, and can be run
again safely, since each run rebuilds a clean database from the CSV. It turns on
foreign keys, inserts through parameterized statements in one transaction, and
depends only on pandas and the standard library, so it runs without installing
anything of mine. It checks the input first and stops with a clear message if
something is wrong, a duplicated sample, a subject with two treatments, or a
subject whose details disagree across rows, rather than quietly loading a
database that is subtly wrong.

A clean run loads 3 projects, 3,500 subjects, 3,500 treatment episodes, 10,500
samples, and 52,500 measurements. I checked the relative frequencies against
numbers worked out by hand, and the test suite covers the row counts, the links
between tables, the response and treatment rule, and the safe re-run. Part 1 is
solid and ready to build on.

## Part 2: Initial analysis, data overview

Part 2 answers the simplest and most important question: for any given sample,
what is the makeup of immune cells. The answer is proportions, not raw counts, so
that two samples can be compared on the same footing even when one was larger
than the other. A sample can then be described as roughly a quarter CD8 T cells
and a tenth B cells regardless of how many cells were collected.

Proportions are necessary because the five columns in the file are absolute
counts, and every sample was collected and processed a little differently, so one
sample might total 93,000 cells and another 60,000. Comparing raw B cell counts
between them would mostly measure how many cells happened to be collected, not the
subject's immune makeup. Converting each population to a percentage of its own
sample's total removes that effect and makes samples comparable. That conversion
is the whole job of Part 2.

The output is a long table, one row per population per sample, with exactly the
columns the brief asked for: sample, total_count, population, count, and
percentage. For each sample I sum the five populations to get the total, then each
percentage is that population's count divided by the total, times one hundred.
Across the whole dataset that is 10,500 samples times five populations, so 52,500
rows. The total repeats across a sample's five rows, which is correct for this
shape. The program builds the table, writes the full version to a CSV, prints a
short preview so the terminal stays readable, and hands the table back so the
dashboard can show it later. As a check, sample00000 comes out as 11.70 percent B
cells, 26.22 percent CD8 T, 21.98 percent CD4 T, 14.87 percent NK, and 25.22
percent monocyte, which sums back to one hundred.

I did not write a new calculation for this. Part 1 already created a database view
that computes exactly this, so Part 2 reads from that one view rather than
recomputing the numbers a second way. This matters more than it sounds. If the
calculation lived in two places, the CSV and the dashboard could one day disagree
over a rounding rule or a fix applied to only one of them. With a single
definition in the database, the number a reader sees in the dashboard is the same
number in the file, always. While doing this I removed an earlier throwaway
version of the same calculation, so relative frequency is now defined in exactly
one place.

I also tightened the precision. Originally the view rounded the percentage as it
stored it, which meant each sample's five percentages added up to 99.9998 or
100.0002 rather than a clean one hundred, because the rounding happened too early
and the lost detail could not be recovered. I changed it so the database keeps the
full precision number and rounding to two decimals happens only at the moment a
person reads the table. Now the underlying percentages sum to exactly one hundred,
and the two decimal figures are purely a display choice. Rounding late instead of
early is a small change that makes the numbers trustworthy.

One naming note. The table has a column literally called count, which is also a
SQL keyword. I kept the name because the specification asks for it and the
database handles it correctly. I am flagging it so it reads as a deliberate choice
rather than an oversight.

Hardening the tests surfaced a real bug. I added a test for the edge case of a
sample whose counts are all zero, and it immediately caught a problem: the code
tried to round a percentage that was empty for such a sample and would have
crashed. The database was already handling the zero total safely by returning an
empty percentage, but the display code was not ready for it. I fixed the display
code to treat an empty percentage as blank rather than choke on it. The real data
has no such sample, so nothing was broken in practice, but the program now handles
an unusual sample cleanly instead of failing.

The summary reads straight from the database view, produces the exact table the
brief asked for, writes it to a CSV, and returns it for the dashboard. It is
covered by tests for the row count, the exact columns and their order, a known
sample's values, the percentages summing to one hundred, the CSV output, a
missing database, and the all-zero sample. Part 2 is done and feeds directly into
the comparison work in Part 3.

## Part 3: Statistical analysis

The question in Part 3 is whether immune cell makeup separates subjects who
respond to miraclib from those who do not. The answer, done properly, is that it
does not. No population separates the two groups at baseline, and the one
on-treatment lead does not survive correction. The rest of this section explains
the cohort, the method, and why counting subjects correctly is what drives the
result.

The cohort is fixed: melanoma subjects on miraclib, PBMC samples only, responders
against non-responders. That is 656 subjects. How those subjects are counted
changes the answer, so I handled the counting first.

Each subject in this cohort gave three samples, at day 0, day 7, and day 14. It is
tempting to pour all 1,968 samples into a single responder versus non-responder
test. That would be wrong, and quietly so. Three samples from one person are not
three independent pieces of evidence, they are one person measured three times, so
treating them as independent triples the apparent sample size and makes p-values
look smaller than they should. This is pseudoreplication, and it manufactures
findings that are not real. I proved it on this data rather than asserting it. For
B cells, pooling all samples gives a p-value of 0.056, right on the edge of
looking significant. Collapsing each subject to a single value moves that same
comparison to 0.35, plainly not significant. The near-hit was an artifact of
counting each subject three times, so I set the pooled approach aside as unsound.

I ran the comparison two honest ways. The primary analysis uses baseline only, the
day 0 sample, one per subject. This is the cleanest possible test and it matches
the goal of prediction, because a signal visible before or at the start of
treatment is what would let the client predict who will respond. The secondary
sensitivity analysis averages each subject across their timepoints into one value,
which uses all the data without the pseudoreplication problem. Two framings, both
valid, and I report both.

Cell frequencies are proportions and are not normally distributed, so I used the
Mann-Whitney U test, which does not assume a normal distribution, rather than a
t-test. For every population I report the median of each group, the p-value, and
an effect size, because a p-value alone does not say how big a difference is, and
a careful reviewer will rightly ask. Because I am testing five populations at
once, I correct for multiple comparisons with the Benjamini-Hochberg method and
rely on the corrected p-values for any claim. Testing five things and celebrating
the one that comes in under 0.05 is exactly how false findings get published.

No immune cell population separates responders from non-responders once the
statistics are done properly. At baseline nothing comes close. In the sensitivity
analysis one population, CD4 T cells, stands out as a lead, with responders
trending higher, but its corrected p-value is about 0.06, just short of
significance. So the honest message is not that there is a predictor. There is one
plausible thread worth a larger study.

The CD4 thread is worth describing carefully, because it appears only when the
on-treatment samples are included, not at baseline. In plain terms, responders and
non-responders start out looking the same, and their CD4 fraction drifts apart
during treatment. That is a difference that emerges as the drug acts, which is
biologically sensible, but it is a difference observed alongside response, not
shown to cause it.

Three figures support this. The boxplot shows the distribution of each population
for responders versus non-responders, and the two groups sit almost on top of each
other, which is the null result made visible. The forest plot shows each
population's effect size with a confidence interval, and every interval crosses
zero, again saying no clear separation. The trajectory plot follows each
population's average over days 0, 7, and 14 for the two groups, and in the CD4
panel the responder line climbs away from the non-responder line after treatment
starts, while at day 0 they are together.

The bottom line for the client is this. There is no baseline biomarker in this
cohort that predicts miraclib response, and the one on-treatment lead, CD4 T cells
rising in responders, is suggestive but does not survive a fair statistical
correction. It is a candidate worth a larger, prespecified study, not a result to
act on yet. This is an observational comparison, so even the CD4 signal is an
association, not proof that the drug drives it. An honest lead is more useful here
than a confident but fragile claim.

## Part 4: Data subset analysis

Part 4 describes a specific slice of the trial to support the study of early
treatment effects. It is not new analysis, it is careful counting, and the value
is in getting the definitions exactly right.

I filtered to melanoma subjects treated with miraclib, PBMC samples, at baseline,
meaning day 0. That gives 656 samples. Because baseline is one sample per subject,
that is also 656 subjects. This is the same starting group as the prediction
analysis in Part 3, and I defined that group in a single place in the code so the
two parts can never drift apart on what the cohort means.

I broke the group down three ways. By project, counting samples, 384 come from
project one and 272 from project three. Project two contributes none to this
group, which is expected, it simply has no melanoma miraclib PBMC baseline
samples, and I note it so nobody wonders where it went. By response, counting
subjects, 331 responders and 325 non-responders, an almost even split, which is
convenient because it means later comparisons are not skewed by one group being
much larger. By sex, counting subjects, 344 males and 312 females.

One detail I was careful about: the question asks for samples per project but
subjects by response and by sex. Those are different units. At baseline they
happen to be one and the same, since each subject has a single sample, but I
counted them the way the question asked, samples where it says samples and
distinct subjects where it says subjects, so the code stays correct even if the
filter later changed to include more timepoints.

A data integrity note belongs on the record. The brief referred to a treatment
called quintazide. That name does not appear anywhere in the dataset. The only
treatments present are miraclib, phauximab, and none, and I confirmed quintazide
is absent from every row of the source file and the database. I did not introduce
it into any result, because reporting a drug that is not in the data would be
misleading.

## The dashboard

The last piece is an interactive dashboard, so the client can explore the analysis
without running any code. It is a Streamlit app, and it starts with make
dashboard, which serves it at localhost:8501. In Codespaces the port is forwarded
automatically.

The most important property of the dashboard is what it does not do: it does not
recompute anything of its own. It reads the same database the pipeline built and
calls the same functions that sit behind Parts 2 to 4, so a number on the screen
is always the same number in the report and in the output files. Making it
impossible for the dashboard to quietly disagree with the written results is worth
more than a second implementation, and a thin layer over already-tested code is how
that guarantee holds.

It has three tabs. Data overview is the Part 2 relative frequency table, with a
search box, filtered by the cohort chosen in the sidebar. Responder analysis is the
Part 3 comparison: the statistics table, the honest conclusion, and the three
figures, with a toggle between the baseline and the per-subject-mean views. That
tab stays fixed to the melanoma miraclib PBMC cohort on purpose, because responders
only exist for treated subjects, so letting the sidebar point it at healthy or
untreated people would ask a question that has no answer. Subset explorer is the
Part 4 view: the counts as metric cards and bar charts, recomputed live for
whatever cohort the sidebar describes.

The sidebar filters, condition, treatment, sample type, and timepoint, drive the
overview and the subset tabs as they change, so exploring a different slice is
immediate. For the look, I stayed with a clean native theme rather than
hand-written styling, because a dashboard that stays readable and easy to maintain
is worth more here than one chasing a pixel-perfect design.
