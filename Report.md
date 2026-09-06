# Immune Cell Analytics Report

Hi team. This is my running write-up of the immune cell count work for Loblaw
Bio. I will add a section as each part lands. For now Part 1, the data
management piece, is done, and this covers how I thought about it and what I
built.

## What I am working with

I have one file, cell-count.csv, with 10,500 blood samples. Each sample carries
five immune cell population counts, b_cell, cd8_t_cell, cd4_t_cell, nk_cell, and
monocyte, along with metadata about the patient and the sample. The overall job
is four analytical parts and an interactive dashboard on top.

One thing I want to flag early, because it will save confusion later: the task
write-up and the actual file use different names for a few columns. In the file,
the patient-facing id is sample (the brief calls it sample_id), the disease is
condition (the brief says indication), and sex is sex (the brief says gender).
The rest line up. The file also has some columns the brief never mentions,
project, subject, age, and sample_type, and I kept all of them. Subject in
particular matters a lot, because it tells me which samples came from the same
person, and the later analysis is not honest without it.

## Part 1: Data Management

The ask here was to design a SQLite database that models the data well and to
write a load_data.py that builds it and loads every row. The interesting part
was not the loading, it was the modeling, so that is what I want to walk you
through.

### Why I did not just load the CSV as one table

A CSV is already a table, so it is tempting to load it straight in and call it a
schema. I did not, and the reason is visible in the data itself. Each patient
gives three samples, and on all three rows the patient's condition, sex, age,
treatment, and response are repeated. When the same fact is written down over
and over, it is only a matter of time before two copies disagree, and every
query has to work around the duplication. That repetition was my signal to pull
the file apart into separate things that each own their own facts.

### Checking my assumptions before trusting them

Before committing to any structure, I checked the shape of the data, because a
model built on a guess tends to break the first time reality disagrees. Three
things came back clean. Every attribute of a patient is identical across that
patient's samples, with no exceptions, so it is safe to store those attributes
once on the patient rather than on each sample. Every patient has exactly one
treatment, so a single course of treatment per patient is the right unit. And
response is filled in for treated patients and blank for the healthy and
untreated ones, with nothing in between, so that blank is telling me something
real rather than being a hole in the data. Because these held perfectly, the
design that follows rests on facts, not hope.

### The shape I landed on

I split the file into five connected pieces. A project holds many patients. A
patient belongs to a project and has one course of treatment. That course of
treatment holds the patient's samples over time. Each sample holds its five cell
measurements. Read the other way, a measurement belongs to a sample, a sample to
a treatment course, a course to a patient, and a patient to a project. It is a
clean chain with nothing pointing back on itself, which keeps every query and
every load straightforward.

### The decision I want to call out

The call I am most confident about is where I put response. In the raw file it
sits on the sample row and is blank for anyone who was not treated, which looks
like missing data and invites people to patch or drop it. It is not missing.
Response is the outcome of a course of treatment, so I attached it to the
treatment record, not the sample. Once it lives there, the blank for an
untreated patient stops being a problem to explain and becomes simply correct,
there was no treatment, so there is no outcome. That one move also gets rid of a
column whose blank would otherwise have meant two different things at once.

### Storing the five counts

I had a choice on the cell counts, five columns side by side, or one row per
population. I went with one row per population. It makes the relative frequency
summary a single clean query instead of five repeated column references, and if
a future panel adds a sixth cell type, that is just more rows rather than a
change to the tables and every query that touches them. The only cost is a few
more rows in one table, which is nothing at this size, so I get the flexibility
essentially for free. I did add a guard so that the population name can only be
one of the five I expect, so the openness never turns into a typo sneaking in.

For anyone wondering whether a vector database belongs here, it does not. That
tool is for finding things that are similar in meaning across unstructured data.
Everything Bob needs is an exact filter, join, or count over structured numbers,
which is exactly what a relational database is built for. I do use fast
vectorized pandas operations inside the loader, but that is a different idea and
not the same as a vector database.

### Letting the database protect the data

I leaned on the database to keep itself honest rather than trusting the loader
to always be careful. Every table has a stable internal key and a unique
constraint on its real-world code, so a genuine duplicate is rejected outright.
The tables are linked so an orphan record cannot exist. Values are constrained to
the sets I expect, counts cannot go negative, and there is a rule that ties
response to treatment, so the database will refuse a row that claims an outcome
with no treatment or a treatment with no outcome. I also added a small view that
returns each population as a percentage of its sample, computed once and safe
against an empty sample, so the later parts read from one agreed definition
instead of each recomputing it.

I indexed only what the later questions actually filter and join on, condition,
response, sample type and timepoint, and the links between tables. I deliberately
did not add indexes on a hunch, because an index nothing uses is just cost.

### The loader itself

load_data.py sits in the root and runs with a plain python load_data.py, no
arguments. It builds cell_count.db in the root, loads everything, and can be run
again safely, since each run rebuilds a clean database from the CSV. It turns on
foreign keys, inserts through parameterized statements in one transaction, and
depends only on pandas and the standard library, so it runs without installing
anything of mine. Importantly, it checks the input first and stops with a clear
message if something is wrong, a duplicated sample, a patient with two
treatments, or a patient whose details disagree across rows, rather than quietly
loading a database that is subtly wrong.

### Where it ended up

A clean run loads 3 projects, 3,500 patients, 3,500 treatment courses, 10,500
samples, and 52,500 measurements. I checked the relative frequencies against
numbers worked out by hand, and there is a test suite covering the row counts,
the links between tables, the response and treatment rule, and the safe re-run.
Part 1 is solid and ready to build on.

## Part 2: Initial Analysis, Data Overview

Bob's first question is the simplest and the most important one to get right:
for any given sample, what is the makeup of immune cells. Not the raw counts,
the proportions. He wants to be able to say a sample is roughly a quarter CD8 T
cells and a tenth B cells, so that two samples can be compared on the same
footing even if one was larger than the other.

### Why proportions and not raw counts

The five columns in the file are absolute counts, and every sample was collected
and processed a little differently, so one sample might total 93,000 cells and
another 60,000. If I compared raw B cell counts between them, I would mostly be
measuring how many cells happened to be collected, not the patient's immune
makeup. Converting each population to a percentage of its own sample's total
removes that effect and makes samples comparable. That conversion is the whole
job of Part 2.

### What I built

The output is a long table, one row per population per sample, with exactly the
columns Bob asked for: sample, total_count, population, count, and percentage.
For each sample I sum the five populations to get the total, then each
percentage is that population's count divided by the total, times one hundred.
Across the whole dataset that is 10,500 samples times five populations, so
52,500 rows. The total repeats across a sample's five rows, which is normal and
correct for this shape.

The program builds this table, writes the full version to a CSV, prints a short
preview so the terminal stays readable, and hands the table back so the
dashboard can show it later. As a quick check, sample00000 comes out as 11.70
percent B cells, 26.22 percent CD8 T, 21.98 percent CD4 T, 14.87 percent NK, and
25.22 percent monocyte, which sums back to one hundred.

### The decision that keeps the parts honest

I did not write a new calculation for this. In Part 1 I had already created a
database view that computes exactly this, so Part 2 reads from that one view
rather than recomputing the numbers a second way. This matters more than it
sounds. If the calculation lived in two places, the CSV and the dashboard could
one day disagree over a rounding rule or a fix applied to only one of them. With
a single definition in the database, the number Bob sees in the dashboard is the
same number in the file, always. While doing this I also removed an earlier
throwaway version of the same calculation, so relative frequency is now defined
in exactly one place.

### Getting precision right

One subtle thing I tightened up here. Originally the view rounded the percentage
as it stored it, which meant each sample's five percentages added up to
99.9998 or 100.0002 rather than a clean one hundred, because the rounding
happened too early and the lost detail could not be recovered. I changed it so
the database keeps the full precision number, and rounding to two decimals
happens only at the moment a person reads the table. Now the underlying
percentages sum to exactly one hundred, and the two decimal figures are purely
a display choice. Rounding late instead of early is a small change that makes
the numbers trustworthy.

One naming note for the team: the table has a column literally called count,
which is also a SQL keyword. I kept the name because Bob's specification asks
for it, and the database handles it correctly. I am flagging it so it reads as a
deliberate choice rather than an oversight.

### A bug worth mentioning

While hardening the tests I added one for the edge case of a sample whose counts
are all zero. That test immediately caught a real problem: the code tried to
round a percentage that was empty for such a sample and would have crashed. The
database was already handling the zero total safely by returning an empty
percentage, but the display code was not ready for it. I fixed the display code
to treat an empty percentage as blank rather than choke on it. The real data has
no such sample, so nothing was broken in practice, but if Bob ever loads an
unusual sample the program now handles it cleanly instead of failing.

### Where it ended up

The summary reads straight from the database view, produces the exact table Bob
asked for, writes it to a CSV, and returns it for the dashboard. It is covered
by tests for the row count, the exact columns and their order, a known sample's
values, the percentages summing to one hundred, the CSV output, a missing
database, and the all zero sample. Part 2 is done and feeds directly into the
comparison work in Part 3.

## Part 3: Statistical Analysis

Bob wants to know whether the immune cell makeup separates patients who respond
to miraclib from those who do not, and he needs it solid enough to convince Yah.
The cohort is fixed: melanoma patients on miraclib, PBMC samples only,
responders (response yes) against non-responders (response no). That is 656
patients, and this is where the analysis gets interesting, because how I count
those patients changes the answer.

### The trap I had to avoid first

Each patient in this cohort gave three samples, at day 0, day 7, and day 14. It
is tempting to pour all of those samples, 1,968 of them, into a single
responder versus non-responder test. That would be wrong, and quietly so. Three
samples from one person are not three independent pieces of evidence, they are
one person measured three times, so treating them as independent triples the
apparent sample size and makes p-values look smaller than they should. This is
called pseudoreplication, and it manufactures findings that are not real.

I proved it on this data rather than just asserting it. For B cells, pooling all
samples gives a p-value of 0.056, right on the edge of looking significant. The
moment I collapse each patient to a single value, that same comparison jumps to
0.35, plainly not significant. The near-hit was an artifact of counting each
patient three times. So I set the pooled approach aside as unsound.

### How I chose to count patients

I ran the comparison two honest ways. The primary analysis uses baseline only,
the day 0 sample, one per patient. This is the cleanest possible test and it
matches the goal of prediction, because a signal you can see before or at the
start of treatment is what would let Bob predict who will respond. The
secondary, sensitivity analysis averages each patient across their timepoints
into one value, which uses all the data without the pseudoreplication problem.
Two framings, both valid, and I report both.

### How I tested for a difference

Cell frequencies are proportions and are not normally distributed, so I used the
Mann-Whitney U test, which does not assume a normal distribution, rather than a
t-test. For every population I report the median of each group, the p-value, and
an effect size, because a p-value alone does not tell you how big a difference
is, and a colleague like Yah will rightly ask. Because I am testing five
populations at once, I also correct for multiple comparisons with the
Benjamini-Hochberg method, and I rely on the corrected p-values for any claim.
Testing five things and celebrating the one that comes in under 0.05 is exactly
how false findings get published.

### What the data actually says

The honest answer is that no immune cell population separates responders from
non-responders once the statistics are done properly. At baseline nothing comes
close. In the sensitivity analysis one population, CD4 T cells, stands out as a
lead, with responders trending higher, but its corrected p-value is about 0.06,
just short of significance. So I am not going to tell Bob he has a predictor. I
am going to tell him he has one plausible thread worth a larger study.

That CD4 thread is worth describing carefully, because it only appears when the
on-treatment samples are included, not at baseline. In plain terms, responders
and non-responders start out looking the same, and their CD4 fraction drifts
apart during treatment. That is a difference that emerges as the drug acts,
which is biologically sensible, but it is a difference observed alongside
response, not shown to cause it.

### The figures

I made three, each answering a different question. The boxplot Bob asked for
shows the distribution of each population for responders versus non-responders,
and the two groups sit almost on top of each other, which is the null result
made visible. The forest plot shows each population's effect size with a
confidence interval, and every interval crosses zero, again saying no clear
separation. The third figure is the one I think tells the real story: the
trajectory plot follows each population's average over days 0, 7, and 14 for the
two groups, and in the CD4 panel you can watch the responder line climb away
from the non-responder line after treatment starts, while at day 0 they are
together.

### What I would tell Bob and Yah

There is no baseline biomarker in this cohort that predicts miraclib response,
and the one on-treatment lead, CD4 T cells rising in responders, is suggestive
but does not survive a fair statistical correction. It is a candidate worth a
larger, prespecified study, not a result to act on yet. This is an
observational comparison, so even the CD4 signal is an association, not proof
that the drug drives it. I would rather hand Bob an honest lead than a
confident but fragile claim.

## Part 4 and the dashboard

More to come as I finish each one.
