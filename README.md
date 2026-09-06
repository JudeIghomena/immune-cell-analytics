# Immune Cell Analytics

Analysis of immune cell population counts from blood samples, with a focus on
converting raw counts to relative frequencies and comparing treatment
responders against non-responders.

## Dataset

`data/cell-count.csv` contains 10,500 samples with sample metadata, clinical
and experimental context, and raw counts for five immune cell populations
(`b_cell`, `cd8_t_cell`, `cd4_t_cell`, `nk_cell`, `monocyte`).

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,analysis]"
pytest
```

## Quality gates

Every push and pull request runs the same checks locally and in CI:

```bash
ruff check .          # lint
ruff format --check . # formatting
mypy                  # static types
pytest                # tests
```

## Branching model

| Branch    | Role                        | Protection                        |
|-----------|-----------------------------|-----------------------------------|
| `main`    | Production. Always green.    | Merges only via reviewed PR + CI  |
| `staging` | Integration. Feature work.  | CI runs on every push             |

Work lands on `staging`, CI verifies it, then a pull request promotes it to
`main` once all checks pass.

## Repository layout

```
src/immune_cell_analytics/   # library code
tests/                       # pytest suite
data/                        # input dataset
.github/workflows/ci.yml     # CI/CD pipeline
```
