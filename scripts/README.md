# Scripts — reproducing and validating the published datasets

The published release (`export/higher_education_cost_cpi_sectors_v1.*`,
`..._tuition_longrun_v1.*`, `..._spending_mix_v1.*`) is rebuildable from raw
sources with a single command, and every headline figure in the four published
charts is re-checked by a pre-publish validation gate.

Use the project virtual environment for both:

```bash
.venv/bin/python scripts/reproduce.py        # raw → export
.venv/bin/python scripts/validate_charts.py  # pre-publish data gate
```

## `reproduce.py` — raw → export

```bash
python scripts/reproduce.py
```

Runs the project's canonical pipeline end to end — the numbered notebooks
`01-ingest` → `02-clean` → `03-prepare` — which contain the exact ingest,
cleaning, and prepare/export logic (the reusable code lives in [`../src/`](../src)).
Running the notebooks is how this project is built, so the reproduced `export/`
matches the published datasets.

| Stage | Notebook | What it does | Output |
|-------|----------|--------------|--------|
| 1. Ingest | `01-ingest` | Ensures the raw BLS CPI-U sector series, NCES Digest 330.10 tuition table, Delta Cost Project zip (~115 MB), and IPEDS finance/tuition files are in `data/raw/` (downloads any that are missing), and loads them into DuckDB as the `*_raw` tables | `data/raw/` + DuckDB raw tables |
| 2. Clean | `02-clean` | Builds the interim `*_clean` tables in DuckDB (`cpi_sectors_clean`, `tuition_longrun_clean`, `spending_mix_clean`, the finance spine) — all cleaning happens in DuckDB SQL | DuckDB `*_clean` tables + `data/interim/` Parquet |
| 3. Prepare | `03-prepare` | Builds the chart-ready `chart_*` tables and packages the sellable datasets (CSV + Excel + Parquet + codebook) | `export/*.{csv,xlsx,parquet}` + codebooks |

Each stage first regenerates its `.ipynb` from the matching `scripts/_build_nb_*.py`
nbformat builder, then executes it in place with `nbconvert`, so a run always
executes the current pipeline code (not a stale checked-in notebook).

### Prerequisites

- Python 3.11+ with the packages in [`../requirements.txt`](../requirements.txt).
  Use the project `.venv` (`.venv/bin/python scripts/reproduce.py`).
- Network access on the **first** run (to download raw files). Once `data/raw/`
  is populated, subsequent runs are fully offline.
- DuckDB is single-writer — close any notebook kernel or DB tool holding
  `data/project.duckdb` before running.
- Source URLs, definitions, and methodology/series-break notes are in
  [`../SOURCES.md`](../SOURCES.md).

### Options

```bash
python scripts/reproduce.py --no-download        # fail (don't fetch) if data/raw/ is empty
python scripts/reproduce.py --stages 02 03       # re-run only clean + prepare (raw already present)
python scripts/reproduce.py --build-only         # (re)generate the notebooks from scripts/, don't execute
```

## `validate_charts.py` — pre-publish data gate

```bash
python scripts/validate_charts.py   # prints "safe to publish" and exits 0 on success
```

Re-derives, straight from the project DuckDB, what each of the four published
charts shows and asserts the exact headline figures — tuition the steepest sector
(index ≈ 1,476 vs All Items ≈ 443), tuition out-ran general inflation by ≈ +233%,
public 4-year real tuition ≈ $2,442 → ≈ $9,872 (~4×), and the honest spending-mix
split (instruction 48.8% → 43.1%, admin flat ≈ 15%, non-instructional 32.5% →
37.4%). It also confirms each published `export/*.csv` still matches its DuckDB
source table (no drift) and that the social/web chart sets stay in parity. Exit
code 0 = safe to publish; non-zero names the failing check. Run it after
`reproduce.py` and before any release.

## Scope

This entrypoint reproduces the three published datasets that back the four release
charts. The project also builds an institution-level combined dataset
(`higher_education_cost_v1`) and additional exploration tables (admin-vs-faculty
headcount, per-state admin, etc.); those run through the same `01→02→03` notebook
pipeline and are not separately curated for the public release.
