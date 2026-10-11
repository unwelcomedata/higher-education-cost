"""Build notebooks/03-prepare.ipynb for higher-education-cost via nbformat.

Run from the project root with the project venv:
    .venv/bin/python scripts/_build_nb_03_prepare.py

Produces the canonical-record prepare notebook: a markdown cell per step
(narrating WHAT + WHY at its pipeline stage) followed by a code cell that calls
the src/prepare.py (shaping) + src/clean_quality.py (save/connection) helpers.

03-prepare has TWO jobs:
  1. BUILD THE CHART-READY TABLES — the shaped/aggregated per-chart tables for
     the admin-vs-instruction-over-time story, FROM the interim `_clean` tables
     (join, per-FTE normalize, deflate to constant-2022-$). Saved to
     data/processed/ and as processed DuckDB `chart_*` tables.
  2. EXPORT THE PACKAGE — strip_pii then package_dataset → CSV + Excel + Parquet
     + a codebook with a plain-English description for EVERY column.

The notebook is executed headless with:
    .venv/bin/python -m nbconvert --to notebook --execute --inplace notebooks/03-prepare.ipynb

Structure/style copied from scripts/_build_nb_02_clean.py.
"""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf

nb = nbf.v4.new_notebook()
cells: list = []


def md(text: str) -> None:
    cells.append(nbf.v4.new_markdown_cell(text.strip("\n")))


def code(text: str) -> None:
    cells.append(nbf.v4.new_code_cell(text.strip("\n")))


# ---------------------------------------------------------------------------
md(
    """
# 03 — Prepare · higher-education-cost

**Goal of this stage — TWO jobs:**

1. **Build the chart-ready / analysis-ready tables.** From the interim `_clean`
   tables (the APPROVED output of `02-clean`), build the shaped/aggregated
   per-chart `chart_*` tables for the **admin-vs-instruction-over-time** story —
   joined, normalized **per 12-month FTE**, and **deflated to constant-2022
   dollars**. This is `03`'s job (every `CREATE TABLE chart_* AS SELECT …` lives
   here, NOT in `04-viz`). Saved to `data/processed/` and as processed DuckDB
   tables.
2. **Export the sellable package.** `strip_pii()` then `package_dataset()` →
   CSV + Excel + Parquet to `export/`, plus a codebook with a plain-English
   description for **every** column.

**Settled methodology (`artifacts/HARMONIZATION-DESIGN.md`), applied here:**

- **"admin" = IPEDS Institutional support ONLY** (`function = institutional_support`)
  — never academic support, never student services.
- Every dollar figure is **per 12-month FTE** (`fte_total` from `fte_clean`),
  in **constant 2022 dollars** via CPI-U All-Items (`cpi_clean`, base 2022).
- **`control` stays a dimension** on every row (`public` = GASB / `private_np` =
  FASB). The two sectors are shown together or split, **never silently pooled**.
- The **share denominator** is the in-pipeline SUM of the harmonized function
  totals (design §1.2 note 3) — **never** a raw IPEDS total line.

**Chart-ready tables built (design §8.1 / PIPELINE-PLAN Stage-03 step 3):**

| processed table | grain | what it feeds |
|---|---|---|
| `spend_per_fte` | UNITID × year × function | the analysis spine (per-FTE + real-2022-$) |
| `chart_admin_vs_instruction_by_sector` | control × year × {instruction, admin} | LEAD chart: admin vs classroom $/FTE |
| `chart_admin_share_trend` | control × year | admin as a share of functional spending |
| `chart_spend_by_function_by_year` | control × year × function | per-FTE $ by function |
| `chart_admin_per_fte_by_state` | stabbr × control | admin $/FTE by state + 2012→2022 change |
| `chart_admin_per_fte_by_state_top_bottom` | stabbr × control | top-5 + bottom-5 states per sector by admin change |
| `chart_tuition_vs_cpi` | year | sticker tuition vs CPI All-Items vs CPI tuition subindex |

**Stage gate:** `04-viz` only begins after these processed + export artifacts
exist on disk; `04` CONSUMES these tables and must not build `chart_*` tables
off interim data.
"""
)

code(
    """
import os
import sys
from pathlib import Path

# Resolve the project root (folder containing config.yaml) and make src importable.
PROJECT = Path.cwd()
while not (PROJECT / "config.yaml").exists() and PROJECT != PROJECT.parent:
    PROJECT = PROJECT.parent
os.chdir(PROJECT)
sys.path.insert(0, str(PROJECT))

import pandas as pd

from src.ingest import load_config
from src import clean_quality as cq
from src import prepare as prep

cfg = load_config("config.yaml")
con = cq.get_connection(cfg)   # opens data/project.duckdb (single-writer!)
print("Project:", cfg["project_name"])
print("DuckDB :", cfg["settings"]["duckdb_file"])
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Step 1 — ⭐ Stage gate: confirm `02-clean` output exists

**Hard stage-order gate (non-negotiable).** `03-prepare` may not begin until
`02-clean` is actually DONE — i.e. the six interim Parquet files exist on disk
and the matching `_clean` DuckDB tables are present. This cell asserts that and
loads the `_clean` tables; it **raises** if any is missing (which would mean
Stage 02 is incomplete and this stage must stop).

Interim tables required: `hd_clean`, `finance_functions_clean`,
`finance_totals_clean`, `fte_clean`, `charges_clean`, `net_price_clean`,
`cpi_clean`.
"""
)

code(
    r"""
REQUIRED_INTERIM = ["hd_clean", "finance_functions_clean", "finance_totals_clean",
                    "fte_clean", "charges_clean", "net_price_clean", "cpi_clean"]
interim_dir = Path(cfg["paths"]["data_interim"])
db_tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}

print(f"{'interim table':<28}{'parquet?':<10}{'db table?':<10}{'rows':>10}")
print("-" * 58)
for t in REQUIRED_INTERIM:
    pq = interim_dir / f"{t}.parquet"
    assert pq.exists(), f"STAGE-02 NOT DONE — missing interim parquet: {pq}"
    assert t in db_tables, f"STAGE-02 NOT DONE — missing _clean DuckDB table: {t}"
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"{t:<28}{'yes':<10}{'yes':<10}{n:>10,}")
print("\n✓ Stage-02 output present — all six interim _clean tables exist. 03-prepare may proceed.")
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Step 2 — `spend_per_fte` (the analysis spine)

Join the harmonized finance spine (`finance_functions_clean`) to `hd_clean`
(for `stabbr / sector / control / iclevel`) and `fte_clean` (for `fte_total`),
stack both years, and compute:

- `amount_per_fte          = amount_nominal / fte_total`
- `amount_per_fte_real2022 = amount_per_fte × (CPI_All_2022 / CPI_All_year)`

so every figure is **dollars per 12-month FTE student, in constant 2022
dollars**. Null/zero-FTE institutions keep their nominal amount but get NULL
per-FTE values (reported below and dropped from per-FTE views). Two integrity
columns are carried: `in_both_years` (institution present in 2012 **and** 2022)
and `control_matches_hd` (the finance-file origin agrees with HD control:
public↔GASB, private_np↔FASB).

**Deflation invariant (asserted below):** 2022 rows have ratio exactly 1.0
(2022 is the base year); 2012 rows are scaled up by exactly the CPI ratio
`CPI_2022 / CPI_2012`.
"""
)

code(
    r"""
spend = prep.build_spend_per_fte(con)
cq.quality_report(spend, "spend_per_fte", con,
                  required_columns=["unitid", "year", "control", "function",
                                    "amount_nominal", "amount_per_fte_real2022"],
                  max_null_pct=0.10)
cq.load_to_duckdb(spend, "spend_per_fte", con)
cq.save_processed(spend, cfg, "spend_per_fte.parquet")
print("Spine rows:", f"{len(spend):,}", "| functions:", sorted(spend['function'].unique()))
"""
)

code(
    r"""
# --- Invariants (design §5 deflation; §4 per-FTE drops; §6 HD-control check) ---
import numpy as np

# CPI anchors used for deflation.
cpi_2012, cpi_2022 = con.execute(
    "SELECT MAX(CASE WHEN year=2012 THEN cpi_all_items END), "
    "       MAX(CASE WHEN year=2022 THEN cpi_all_items END) FROM cpi_clean"
).fetchone()
expected_2012_ratio = cpi_2022 / cpi_2012
print(f"CPI All-Items: 2012={cpi_2012}, 2022={cpi_2022}  ->  2012 deflation factor = {expected_2012_ratio:.5f}")

d = spend.dropna(subset=["amount_per_fte", "amount_per_fte_real2022"]).copy()
d["ratio"] = d["amount_per_fte_real2022"] / d["amount_per_fte"]
r22, r12 = d[d.year == 2022]["ratio"], d[d.year == 2012]["ratio"]
# Use per-year min/max (robust) rather than a whole-frame allclose.
assert np.isclose(r22.min(), 1.0) and np.isclose(r22.max(), 1.0), "2022 real != nominal"
assert np.isclose(r12.min(), expected_2012_ratio) and np.isclose(r12.max(), expected_2012_ratio), \
    "2012 deflation factor is not the CPI ratio"
print("✓ Deflation OK — 2022 ratio exactly 1.0; 2012 ratio exactly the CPI ratio.")

# Per-FTE drop count (null/zero FTE) by year.
drops = cq.run_sql(
    "SELECT year, COUNT(*) FILTER (WHERE amount_per_fte IS NULL) AS dropped_per_fte, "
    "COUNT(*) AS rows FROM spend_per_fte GROUP BY year ORDER BY year", con)
print("\nPer-FTE drops (null/zero FTE, kept in absolute views only):")
print(drops.to_string(index=False))

# HD-control agreement: report mismatches (do NOT hard-fail — a known IPEDS reality
# where a handful of institutions file the other standard's finance form).
mism = cq.run_sql(
    "SELECT control AS finance_origin, hd_control, COUNT(*) AS rows "
    "FROM spend_per_fte WHERE control_matches_hd = FALSE "
    "GROUP BY control, hd_control ORDER BY rows DESC", con)
n_mismatch = int(mism["rows"].sum()) if len(mism) else 0
print(f"\nControl mismatches (finance origin vs HD control): {n_mismatch:,} of {len(spend):,} rows")
if len(mism):
    print(mism.to_string(index=False))
print("in_both_years rows:", int(spend['in_both_years'].sum()))
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Step 3 — the five chart-ready tables

Each is a DuckDB-SQL aggregate of `spend_per_fte`, built by a `src/prepare.py`
helper, saved to `data/processed/` and created as a processed DuckDB table. This
is `03`'s shaping job — `04-viz` only READS these.

### 3a · `chart_admin_vs_instruction_by_sector` — the LEAD chart

`control × year × {instruction, institutional_support}`: mean (and median)
per-FTE real-2022-$ across institutions. The direct "admin vs classroom dollars
per student, public vs private, 2012 vs 2022" cut. **Admin = institutional
support only.**
"""
)

code(
    r"""
c1 = prep.build_chart_admin_vs_instruction_by_sector(con)
cq.load_to_duckdb(c1, "chart_admin_vs_instruction_by_sector", con)
cq.save_processed(c1, cfg, "chart_admin_vs_instruction_by_sector.parquet")
print(c1.to_string(index=False))
"""
)

md(
    """
### 3b · `chart_admin_share_trend` — admin as a share of functional spending

`control × year`: institutional-support dollars as a share of the single
§1.2-note-3 denominator = SUM over {instruction, research, public_service,
student_services, institutional_support}, built **identically per sector** from
the in-pipeline function totals (**never** a raw IPEDS total line). Computed at
the institution level then averaged, so each school weighs equally.
"""
)

code(
    r"""
c2 = prep.build_chart_admin_share_trend(con)
cq.load_to_duckdb(c2, "chart_admin_share_trend", con)
cq.save_processed(c2, cfg, "chart_admin_share_trend.parquet")
print(c2.to_string(index=False))

# Assert the share denominator is the in-pipeline function sum, NOT any raw total:
# recompute the public-2022 admin share directly from spend_per_fte and compare.
check = con.execute(
    '''
    WITH pu AS (
      SELECT unitid,
             SUM(amount_nominal) FILTER (WHERE function IN
               ('instruction','research','public_service','student_services','institutional_support')) AS denom,
             SUM(amount_nominal) FILTER (WHERE function='institutional_support') AS admin
      FROM spend_per_fte WHERE year=2022 AND control='public' GROUP BY unitid)
    SELECT AVG(admin/NULLIF(denom,0)) FROM pu
    '''
).fetchone()[0]
reported = float(c2[(c2.control == "public") & (c2.year == 2022)]["mean_admin_share"].iloc[0])
assert abs(check - reported) < 1e-9, (check, reported)
print(f"\n✓ Share denominator = in-pipeline function sum (public-2022 admin share {reported:.4f} reproduced).")
"""
)

md(
    """
### 3c · `chart_spend_by_function_by_year` — per-FTE $ by function

`control × year × function`: mean per-FTE real-2022-$ for all six harmonized
functions. `academic_support` is carried **per sector** (its own `control`
rows); any chart consuming this must keep `academic_support` single-sector and
never place it in a public-vs-private comparison (design §1.2 handling note 1) —
a viz constraint, documented here.
"""
)

code(
    r"""
c3 = prep.build_chart_spend_by_function_by_year(con)
cq.load_to_duckdb(c3, "chart_spend_by_function_by_year", con)
cq.save_processed(c3, cfg, "chart_spend_by_function_by_year.parquet")
print(c3.to_string(index=False))
"""
)

md(
    """
### 3d · `chart_admin_per_fte_by_state` — admin $/FTE by state, with 2012→2022 change

`stabbr × control`: mean institutional-support-per-FTE real-2022-$ in each year,
plus the absolute (`admin_change`) and percent (`admin_pct_change`) change
2012→2022. Only two-letter US state/DC postal codes are kept so a state map
reads cleanly; change columns are NULL where a sector had no institutions in a
year.
"""
)

code(
    r"""
c4 = prep.build_chart_admin_per_fte_by_state(con)
cq.load_to_duckdb(c4, "chart_admin_per_fte_by_state", con)
cq.save_processed(c4, cfg, "chart_admin_per_fte_by_state.parquet")
print("States × sectors:", len(c4), "| distinct states:", c4['stabbr'].nunique())
print(c4.head(12).to_string(index=False))
"""
)

md(
    """
### 3f · `chart_admin_per_fte_by_state_top_bottom` — the 5 largest-rising + 5 largest-falling states per sector

**WHAT:** the by-state cut above has ~100+ states per sector, which is unreadable
as a bar chart. This table keeps, **per `control`**, only the **5 states where
admin-per-FTE rose the most and the 5 where it fell the most** over 2012→2022
(ranked by `admin_change`, the constant-2022-$ change in institutional-support per
FTE) — i.e. **top 5 + bottom 5 = 10 bars**.

**WHY:** the owner asked for a top-5 + bottom-5 view (10 bars total in the chart),
not the full ~100-row diverging chart. Selection is a data-shaping op, so it lives
here in `03-prepare`; `04-viz` only consumes the result. A `band` column marks
'top' (rising) vs 'bottom' (falling); rows stay ordered `control, admin_change` so
the diverging-bars render reads bottom→top. States missing a sector in either year
(NULL change) are excluded; a sector with ≤10 eligible states keeps all of them
(still ≤10 bars).
"""
)

code(
    r"""
c4b = prep.build_chart_admin_per_fte_by_state_top_bottom(con)
cq.load_to_duckdb(c4b, "chart_admin_per_fte_by_state_top_bottom", con)
cq.save_processed(c4b, cfg, "chart_admin_per_fte_by_state_top_bottom.parquet")
print("Rows per control (should be 10 each, or <=10 if a sector has fewer eligible states):")
print(c4b.groupby("control").size().to_string())
print()
print(c4b[["stabbr", "control", "band", "admin_change", "admin_pct_change"]].to_string(index=False))
"""
)

md(
    """
### 3e · `chart_tuition_vs_cpi` — sticker tuition vs CPI All-Items vs CPI tuition subindex

`year` (national): the CPI-U All-Items and college-tuition subindex (both
indexed to **2012 = 100** for a clean "how fast did each rise" comparison), plus
the national mean **sticker** tuition (public in-state / out-of-state, private)
for **both 2012 and 2022**. Sticker only — kept distinct from Scorecard net
price (design §7).

> **✅ Tuition is now on a constant-2022-dollar basis (consistency with the
> finance tables).** Every OTHER chart in this project is in **constant 2022
> dollars** — the per-FTE finance tables are `*_per_fte_real2022`, deflated with
> the CPI-U **All-Items** index (2012 scaled by `CPI_2022 / CPI_2012 =
> 292.655 / 229.594 = 1.27466`). The tuition table previously carried only
> **nominal** sticker dollars, so a 2012→2022 tuition comparison would have mixed
> nominal-vs-real against the finance charts. This builder now adds
> `*_real2022` tuition columns next to the `*_nominal` ones: each year's nominal
> mean is multiplied by the SAME CPI-U All-Items deflator
> (`CPI_All_2022 / CPI_All_year`), read **live from `cpi_clean`** (not
> hardcoded). 2012 is scaled up by 1.27466; 2022 is unchanged (its deflator is
> 1.0, as 2022 is the base year). **The charted/trend value is the `*_real2022`
> column**; the `*_nominal` columns are retained for provenance.
>
> **New columns (plain-English):**
> - `cpi_all_deflator_to_2022` — CPI-U All-Items factor applied to this year's
>   nominal tuition to restate it in constant 2022 dollars (1.0 for 2022).
> - `mean_tuition_public_in_state_nominal` / `..._out_state_nominal` /
>   `mean_tuition_private_nominal` — mean sticker tuition & fees, nominal
>   (as-reported) current-year dollars, by sector.
> - `mean_tuition_public_in_state_real2022` / `..._out_state_real2022` /
>   `mean_tuition_private_real2022` — the same means in **constant 2022 dollars**
>   (CPI-U All-Items deflated); these are the charted values.

> **✅ 2012 sticker tuition is now REAL (upstream fix applied).** The IPEDS
> **IC2012_AY** file had originally been ingested malformed — every `UNITID` and
> tuition value in `ipeds_charges_2012_raw` read as the literal string **`"R"`**.
> That defect was **repaired at `01-ingest`** (an `index_col=False` fix in the
> IPEDS reader so the row-label column no longer shifted every field), and
> `02-clean` was re-run, so `charges_clean` now carries **real non-null 2012
> sticker tuition** (4,455 institutions). This table therefore now carries CPI
> All-Items + the tuition subindex across the full 2012–2022 window **and real
> sticker-tuition dollars (nominal + constant-2022) for BOTH 2012 and 2022** — a
> tuition-dollars-over-time comparison can be drawn directly on the same
> constant-2022-$ basis as the finance charts. (Sticker price stays
> kept-distinct from Scorecard net price per design §7.)
"""
)

code(
    r"""
c5 = prep.build_chart_tuition_vs_cpi(con)
cq.load_to_duckdb(c5, "chart_tuition_vs_cpi", con)
cq.save_processed(c5, cfg, "chart_tuition_vs_cpi.parquet")
print(c5.to_string(index=False))

# Confirm sticker tuition is now real for BOTH endpoint years (2012 and 2022).
yrs_with_tuition = int((c5["n_tuition_reported"].fillna(0) > 0).sum())
endpoint_rows = c5[c5["year"].isin([2012, 2022])][
    ["year",
     "mean_tuition_public_in_state_nominal", "mean_tuition_public_in_state_real2022",
     "mean_tuition_public_out_state_nominal", "mean_tuition_public_out_state_real2022",
     "mean_tuition_private_nominal", "mean_tuition_private_real2022",
     "n_tuition_reported"]
]
print(f"\nYears with usable sticker tuition: {yrs_with_tuition} of {len(c5)}.")
print("Endpoint sticker tuition — nominal vs constant-2022-$ (2012 now REAL after the IC2012_AY fix):")
print(endpoint_rows.to_string(index=False))
assert float(c5[c5.year == 2012]["n_tuition_reported"].iloc[0]) > 0, \
    "2012 sticker tuition still missing — upstream 01/02 fix not applied?"
assert float(c5[c5.year == 2022]["n_tuition_reported"].iloc[0]) > 0, "2022 sticker tuition missing"
print("\n✓ Both 2012 and 2022 carry real sticker-tuition dollars.")
"""
)

md(
    """
#### Deflation assertion — tuition is now constant-2022-$ (consistent with the finance spine)

Prove the new `*_real2022` tuition columns were deflated with the SAME CPI-U
All-Items deflator the finance spine uses:

- **2012 real = 2012 nominal × (CPI_2022 / CPI_2012) = 2012 nominal × 1.27466**
  for all three sectors.
- **2022 real = 2022 nominal** (2022 is the base year; its deflator is exactly 1.0).

The deflator is read live from `cpi_clean`, so this ties the tuition basis to the
same numbers used by `amount_per_fte_real2022`.
"""
)

code(
    r"""
import numpy as np

# Deflator read live from cpi_clean — the SAME CPI-U All-Items ratio the finance spine uses.
cpi_2012_v, cpi_2022_v = con.execute(
    "SELECT MAX(CASE WHEN year=2012 THEN cpi_all_items END), "
    "       MAX(CASE WHEN year=2022 THEN cpi_all_items END) FROM cpi_clean"
).fetchone()
deflator = cpi_2022_v / cpi_2012_v
print(f"CPI All-Items 2012={cpi_2012_v}, 2022={cpi_2022_v}  ->  2012 deflator = {deflator:.5f} (known 1.27466)")
assert np.isclose(deflator, 1.27466, atol=1e-5), "deflator drifted from the documented 1.27466"

r12 = c5[c5.year == 2012].iloc[0]
r22 = c5[c5.year == 2022].iloc[0]
for nom, real, nice in [
    ("mean_tuition_public_in_state_nominal",  "mean_tuition_public_in_state_real2022",  "public in-state"),
    ("mean_tuition_public_out_state_nominal", "mean_tuition_public_out_state_real2022", "public out-of-state"),
    ("mean_tuition_private_nominal",          "mean_tuition_private_real2022",          "private nonprofit"),
]:
    # 2012: real == nominal * deflator
    assert np.isclose(r12[real], r12[nom] * deflator), f"2012 {nice} real != nominal*{deflator:.5f}"
    # 2022: real == nominal (base year)
    assert np.isclose(r22[real], r22[nom]), f"2022 {nice} real != nominal"
    print(f"  {nice:<20} 2012 nom ${r12[nom]:,.0f} ×{deflator:.5f} = real ${r12[real]:,.0f}  |  "
          f"2022 nom ${r22[nom]:,.0f} = real ${r22[real]:,.0f}")
# Confirm the per-row deflator column matches too.
assert np.isclose(float(r12["cpi_all_deflator_to_2022"]), deflator)
assert np.isclose(float(r22["cpi_all_deflator_to_2022"]), 1.0)
print("\n✓ Tuition deflation verified — 2012 real = 2012 nominal × 1.27466; 2022 real = 2022 nominal.")
"""
)

md(
    """
### Confirm all processed artifacts exist

Every chart-ready table must be on disk (Parquet) and in DuckDB before the
export step and before `04-viz` may begin.
"""
)

code(
    r"""
PROCESSED = ["spend_per_fte",
             "chart_admin_vs_instruction_by_sector", "chart_admin_share_trend",
             "chart_spend_by_function_by_year", "chart_admin_per_fte_by_state",
             "chart_admin_per_fte_by_state_top_bottom",
             "chart_tuition_vs_cpi"]
processed_dir = Path(cfg["paths"]["data_processed"])
db_tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
print(f"{'processed table':<42}{'parquet?':<10}{'db?':<6}{'rows':>8}")
print("-" * 66)
for t in PROCESSED:
    pq = processed_dir / f"{t}.parquet"
    assert pq.exists(), f"missing processed parquet: {pq}"
    assert t in db_tables, f"missing processed DuckDB table: {t}"
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"{t:<42}{'yes':<10}{'yes':<6}{n:>8,}")
print("\n✓ All six processed tables written (Parquet + DuckDB).")
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Step 4 — Export the sellable package

Export the **analysis spine** (`spend_per_fte`) as the sellable dataset:
`strip_pii()` first (honoring `export.strip_pii_columns` in `config.yaml`,
currently empty — nothing to drop), then `package_dataset()` → **CSV + Excel +
Parquet** to `export/`, plus a **codebook with a plain-English description for
every column** and `notes` carrying the source/license and the load-bearing
caveats.

The spine is the right export grain: one row per institution × year × function,
with both nominal and constant-2022-$ per-FTE values, so a buyer can reproduce
every chart (admin vs classroom, by sector, by state, over time) from a single
tidy table. The codebook `descriptions` dict covers **every** exported column —
no column is left with the `_No description provided._` placeholder.
"""
)

code(
    r"""
CODEBOOK = {
    "unitid":    "IPEDS UNITID — the unique federal identifier for each postsecondary institution.",
    "year":      "Collection year of the finance data: 2012 (FY 2011-12) or 2022 (FY 2021-22).",
    "control":   "Finance-reporting sector / accounting standard: 'public' (GASB form F1A) or "
                 "'private_np' (private nonprofit, FASB form F2). Carried on every row so the two "
                 "sectors can be split or shown together, never silently pooled.",
    "function":  "Harmonized IPEDS expense-by-function category: instruction, research, "
                 "public_service, academic_support, student_services, or institutional_support. "
                 "'institutional_support' is the project's definition of 'admin'.",
    "source_col": "The raw IPEDS column this amount came from (GASB F1C* / FASB F2E*) — provenance "
                  "for the GASB↔FASB harmonization crosswalk.",
    "amount_nominal": "Expenses for this function, in nominal (as-reported) current-year US dollars.",
    "instnm":    "Institution name (from the IPEDS HD directory file).",
    "stabbr":    "US state / territory two-letter postal abbreviation of the institution.",
    "sector":    "IPEDS SECTOR code (0-9, 99): combines level (4yr/2yr/<2yr) and control; see IPEDS docs.",
    "hd_control": "IPEDS HD CONTROL code: 1 = public, 2 = private nonprofit, 3 = private for-profit.",
    "iclevel":   "IPEDS institution level: 1 = 4-year+, 2 = 2-but-less-than-4-year, 3 = less-than-2-year.",
    "fte_total": "12-month full-time-equivalent enrollment (IPEDS EFIA: FTEUG + FTEGD). The per-FTE "
                 "denominator. NULL/0 where FTE was not reported.",
    "cpi_year":  "CPI-U All-Items annual-average index value for this row's collection year "
                 "(2012 or 2022), used as the inflation deflator.",
    "amount_per_fte": "amount_nominal / fte_total — nominal dollars spent on this function per FTE "
                      "student. NULL where FTE is missing/zero.",
    "amount_per_fte_real2022": "amount_per_fte deflated to constant 2022 dollars via CPI-U All-Items "
                               "(× CPI_2022 / CPI_year). The headline comparable metric; NULL where "
                               "FTE is missing/zero.",
    "in_both_years": "TRUE if this institution reported finance data in BOTH 2012 and 2022 (use for a "
                     "like-for-like over-time panel; the all-institutions view includes enter/exit).",
    "control_matches_hd": "TRUE if the finance-file origin agrees with the HD control code "
                          "(public↔GASB / private_np↔private-nonprofit). FALSE flags the small set of "
                          "institutions that filed the other standard's finance form.",
}

NOTES = '''
Source: U.S. Dept. of Education — IPEDS (NCES) Finance (GASB F1A + FASB F2),
Institutional Characteristics (HD), and 12-month FTE (EFIA); College Scorecard
(net price, separate table); BLS CPI-U (inflation). All are U.S. federal
government works in the public domain. Retrieved 2026-09-30.

Metric: spending per 12-month FTE student, in constant 2022 dollars (CPI-U
All-Items deflator, base year 2022). "Admin" = IPEDS Institutional support ONLY
(not academic support, not student services).

Load-bearing caveats:
- GASB (public) isolates operation-and-maintenance of plant as its own function;
  FASB (private nonprofit) distributes it into the other functions. The
  harmonized functions are comparable only to within that O&M-allocation
  difference; raw per-standard totals are never compared across standards. O&M is
  deliberately excluded from the admin-vs-classroom numerators.
- control stays a dimension on every row — public and private-nonprofit are shown
  together or split, never pooled without the control breakdown being explicit.
- IPEDS survey definitions shifted 2011-12 vs 2021-22; the two years are treated
  as separate series, not a continuous panel. Institutions enter/exit between
  years (use in_both_years for a like-for-like panel).
- A small set of institutions file the other standard's finance form; see
  control_matches_hd.
- Sticker tuition (IPEDS IC) and net price (College Scorecard) are different
  quantities, kept in separate tables and never combined. The IPEDS IC2012_AY
  charges file was originally ingested malformed (every value read as the literal
  "R"); this was repaired upstream at 01-ingest (index_col=False fix) and 02-clean
  re-run, so 2012 sticker tuition is now real. The tuition-vs-CPI view carries CPI
  across the full 2012-2022 window and real sticker-tuition dollars for BOTH years.
'''.strip()

# Verify the codebook covers every exported column (after strip_pii).
export_df = prep.strip_pii(spend.copy(), cfg)
missing_desc = [c for c in export_df.columns if c not in CODEBOOK]
assert not missing_desc, f"codebook missing descriptions for: {missing_desc}"
print("✓ Codebook covers every exported column:", list(export_df.columns))

written = prep.package_dataset(
    spend, cfg, name="higher_education_cost_v1",
    codebook=CODEBOOK, notes=NOTES,
)
print("\nFiles written:")
for fmt, p in written.items():
    print(f"  {fmt:<9} {p}  ({p.stat().st_size:,} bytes)")
"""
)

code(
    r"""
# Confirm every export file exists and the codebook has NO placeholder description.
export_dir = Path(cfg["paths"]["export"])
name = "higher_education_cost_v1"
expected = {
    "csv":      export_dir / f"{name}.csv",
    "xlsx":     export_dir / f"{name}.xlsx",
    "parquet":  export_dir / f"{name}.parquet",
    "codebook": export_dir / f"{name}_codebook.md",
}
for kind, p in expected.items():
    assert p.exists() and p.stat().st_size > 0, f"missing/empty export: {p}"
    print(f"  {kind:<9} OK  {p}")

cb_text = expected["codebook"].read_text(encoding="utf-8")
assert "_No description provided._" not in cb_text, "codebook has placeholder description(s)"
print("\n✓ CSV + Excel + Parquet + codebook all exist; codebook has a real description for every column.")
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Cleanup

DuckDB is single-writer — a notebook that leaves its connection open holds a
lock that blocks other notebooks, scripts, and DBCode. Always close it.
"""
)

code(
    """
con.close()
print("DuckDB connection closed.")
"""
)

md(
    """
---
**Next:** `04-viz.ipynb` (EXPLORATION ONLY) — open DuckDB **read-only** and
CONSUME the `chart_*` processed tables built here to explore the
admin-vs-instruction story, rendering every chart inline. `04` must NOT build
`chart_*` tables off interim data; if exploration reveals a needed new cut, the
fix goes BACK into this notebook (`03-prepare`) and `03` is re-run.
"""
)

# ---------------------------------------------------------------------------
nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}

out = Path("notebooks/03-prepare.ipynb")
nbf.write(nb, str(out))
print("Wrote", out, "with", len(cells), "cells")
