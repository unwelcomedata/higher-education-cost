#!/usr/bin/env python
"""Reproduce the higher-education-cost published datasets from raw sources.

This is the serious-tier reproducibility entrypoint: a single command that goes
from the raw BLS CPI-U, NCES Digest, Delta Cost Project, and IPEDS finance files
all the way to the published ``export/`` datasets the release is built on —
``higher_education_cost_cpi_sectors_v1`` (charts 1 & 2),
``higher_education_cost_tuition_longrun_v1`` (chart 3), and
``higher_education_cost_spending_mix_v1`` (chart 4), each with its codebook.

It runs the project's own canonical pipeline — the numbered notebooks
``01-ingest`` → ``02-clean`` → ``03-prepare`` — which contain the exact ingest,
cleaning, and prepare/export logic (the reusable code lives in ``src/``:
``ingest.py``, ``clean_quality.py``, ``prepare.py``). Running the notebooks is
how this project is built, so the reproduced ``export/`` matches the published
datasets. The pipeline is DuckDB-single-writer, so each notebook is executed in
order against the one project DuckDB file.

Why the notebooks and not a bespoke src-only driver: several steps (e.g. the
CPI-sector re-indexing in ``02-clean`` and the chart-table assembly in
``03-prepare``) are expressed as pipeline SQL in the notebook cells rather than a
single ``src`` function, and the notebooks ARE the canonical record of the
project. Re-running them is the faithful, drift-free reproduction path. The
``src`` modules are still the implementation the notebooks call throughout.

What it does, in order:
  1. INGEST  (``01-ingest``) — ensure raw sources are present in ``data/raw/``
             (downloads any missing BLS CPI-U sector series, NCES Digest 330.10
             tuition table, Delta Cost Project zip (~115 MB), and IPEDS finance /
             tuition files) and load them into DuckDB as the ``*_raw`` tables.
  2. CLEAN   (``02-clean``) — build the interim ``*_clean`` tables in DuckDB
             (``cpi_sectors_clean``, ``tuition_longrun_clean``,
             ``spending_mix_clean``, the finance spine, …), all in DuckDB SQL.
  3. PREPARE (``03-prepare``) — build the chart-ready ``chart_*`` tables and
             package the ``export/`` datasets (CSV + Excel + Parquet + codebook).

After a run, validate the published figures with::

    python scripts/validate_charts.py   # must print "safe to publish", exit 0

Usage::

    python scripts/reproduce.py                 # full run: raw → export
    python scripts/reproduce.py --no-download    # fail instead of fetching missing raw files
    python scripts/reproduce.py --stages 01 02 03   # run a subset of stages
    python scripts/reproduce.py --build-only        # (re)generate notebooks from scripts/, don't execute

Prerequisites:
  - Python 3.11+ with the packages in ``requirements.txt`` (use the project
    ``.venv``: ``.venv/bin/python scripts/reproduce.py``).
  - Network access on the first run (to download raw files). Subsequent runs are
    offline once ``data/raw/`` is populated.
  - Source URLs, definitions, and methodology/series-break notes are in
    ``SOURCES.md``.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
SCRIPTS = PROJECT / "scripts"
NOTEBOOKS = PROJECT / "notebooks"

# The canonical raw → export pipeline, in order. Each stage is (notebook stem,
# nbformat builder script). The builder regenerates the .ipynb from source so a
# run always executes the current pipeline code, not a stale checked-in notebook.
STAGES: list[tuple[str, str]] = [
    ("01-ingest", "_build_nb_01_ingest.py"),
    ("02-clean", "_build_nb_02_clean.py"),
    ("03-prepare", "_build_nb_03_prepare.py"),
]

# Raw-source globs that signal "ingest already ran" (used by --no-download).
RAW_SIGNALS = [
    "data/raw/cpi_u/cpi_sectors_raw.csv",   # BLS CPI-U sector sub-indices
    "data/raw",                             # NCES Digest / Delta / IPEDS land here
]


def _rule(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}", flush=True)


def _run(cmd: list[str], label: str) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=str(PROJECT))
    if result.returncode != 0:
        raise SystemExit(f"{label} failed (exit {result.returncode}).")


def build_notebook(builder: str) -> None:
    """Regenerate a notebook .ipynb from its nbformat builder script."""
    _run([sys.executable, str(SCRIPTS / builder)], f"build {builder}")


def execute_notebook(stem: str) -> None:
    """Execute a notebook in place with nbconvert (same interpreter / venv)."""
    nb = NOTEBOOKS / f"{stem}.ipynb"
    _run(
        [sys.executable, "-m", "nbconvert", "--to", "notebook",
         "--execute", "--inplace", "--ExecutePreprocessor.timeout=1800", str(nb)],
        f"execute {stem}",
    )


def have_raw() -> bool:
    for sig in RAW_SIGNALS:
        p = PROJECT / sig
        if p.is_file() or (p.is_dir() and any(p.rglob("*"))):
            return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Reproduce the higher-education-cost published exports from raw sources.")
    ap.add_argument("--no-download", action="store_true",
                    help="Do not fetch missing raw files; fail if data/raw/ is empty.")
    ap.add_argument("--stages", nargs="+", default=None,
                    help="Subset of stage stems to run (e.g. 01 02 03 or 01-ingest).")
    ap.add_argument("--build-only", action="store_true",
                    help="Only (re)generate the notebooks from scripts/; do not execute them.")
    args = ap.parse_args()

    # Resolve the requested stages (accept '01' or '01-ingest').
    stages = STAGES
    if args.stages:
        wanted = {s.split("-")[0] for s in args.stages}
        stages = [(stem, b) for (stem, b) in STAGES if stem.split("-")[0] in wanted]
        if not stages:
            raise SystemExit(f"No matching stages in {args.stages!r}.")

    _rule("higher-education-cost · reproduce  (raw → export)")
    print(f"Project : {PROJECT}")
    print(f"Stages  : {', '.join(stem for stem, _ in stages)}")
    print(f"Mode    : {'build-only' if args.build_only else 'build + execute'}")

    if args.no_download and not have_raw():
        raise SystemExit(
            "data/raw/ is empty and --no-download was set. Populate the raw sources "
            "from the URLs in SOURCES.md (BLS CPI-U sector series, NCES Digest 330.10, "
            "Delta Cost Project zip, IPEDS finance/tuition files), or re-run without "
            "--no-download so 01-ingest fetches them."
        )

    for i, (stem, builder) in enumerate(stages, start=1):
        _rule(f"{i}/{len(stages)}  {stem}")
        build_notebook(builder)
        if not args.build_only:
            execute_notebook(stem)

    _rule("DONE")
    if args.build_only:
        print("Notebooks regenerated (not executed).")
    else:
        print("Reproduced the published exports in export/:")
        for name in ("higher_education_cost_cpi_sectors_v1",
                     "higher_education_cost_tuition_longrun_v1",
                     "higher_education_cost_spending_mix_v1"):
            print(f"  - {name}.csv (+ .xlsx / .parquet / _codebook.md)")
        print("\nNext: python scripts/validate_charts.py  "
              "(must print 'safe to publish', exit 0)")


if __name__ == "__main__":
    main()
