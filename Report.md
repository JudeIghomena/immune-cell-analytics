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

## Parts 2 to 4 and the dashboard

More to come as I finish each one.
