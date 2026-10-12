"""Build notebooks/04-viz.ipynb for higher-education-cost via nbformat.

Run from the project root with the project venv:
    .venv/bin/python scripts/_build_nb_04_viz.py

STAGE 04-viz — EXPLORATION ONLY. This notebook CONSUMES the chart-ready
`chart_*` processed tables that 03-prepare produced; it does NOT create any
chart_* tables off interim _clean data. DuckDB is opened read_only and closed
in a ## Cleanup cell.

RENDERING ENGINE — the shared Pillow chart factory, not matplotlib.
matplotlib on this project's .venv (Python 3.14) RecursionErrors on *any*
figure draw/savefig (an infinite Path.__deepcopy__ loop — confirmed, and NOT
fixable by raising the recursion limit; it is unrelated to set_xticks /
PercentFormatter specifically). So, per the PIPELINE-PLAN fallback and the
dungeon-crawler-carl / presidential-speeches precedent, exploration charts are
built with the shared Pillow factory at ../../shared (chart_factory builders),
each returning a PIL image that is display()'d INLINE. This is the SAME engine
social export would use, so what we explore is what would ship.
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
# 04 — Viz (exploration) · higher-education-cost

**Stage gate.** This is **exploration only**. It runs *after* `03-prepare`,
which produced the chart-ready tables in `data/processed/` and the
`export/higher_education_cost_v1.*` package. This notebook **only consumes**
those `chart_*` tables — it opens DuckDB **read-only** and never builds a
`chart_*` table off interim `_clean` data. If a cut is missing, the fix goes
back into `03-prepare`, not here.

**Goal.** Explore the "admin vs classroom" story — does spending shift toward
*institutional support* (administration) relative to *instruction* over the
decade 2012 → 2022, and how does that differ by sector (public vs private
nonprofit) and by state? Plus how college tuition prices moved against general
inflation.

**Key definitions carried from 03 / SOURCES.md (state these on every chart):**
- **"Admin" = IPEDS `institutional_support`** (executive/management, legal,
  fiscal, HR, general administration). It is the closest IPEDS proxy for
  "administration"; it is **not** all non-instructional spend.
- **"Classroom" = `instruction`.**
- All spend figures are **per 12-month FTE student**, deflated to
  **constant 2022 dollars** (CPI-U All Items).
- **GASB (public) and FASB (private nonprofit) use different expense-function
  definitions** and are not perfectly 1:1 — public vs private comparisons are
  indicative, not exact. `academic_support` is shown **per sector only**, never
  as a cross-sector comparison.

**Titles describe, they don't conclude.**

**Rendering note:** matplotlib RecursionErrors on this venv (Python 3.14), so
every chart below is built with the **shared Pillow factory** (`../../shared`)
and shown inline. These are exploratory renders for owner review — no
`06-viz-social` / web rendering is built here.
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

# Shared Pillow chart factory (matplotlib is unusable on this venv).
SHARED = PROJECT.parent.parent / "shared"
sys.path.insert(0, str(SHARED))

import duckdb
import pandas as pd
from IPython.display import display

from colors import c
import chart_factory as cf

DB = PROJECT / "data" / "project.duckdb"


def show(img):
    \"\"\"Display a PIL image returned by a factory builder inline (no file write).\"\"\"
    display(img)


print("Project:", PROJECT.name)
print("Shared :", SHARED)
print("DuckDB :", DB)
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Stage-03 precondition guard + read-only connection

Assert the processed `chart_*` tables and the `export/` package 03 produced
exist on disk, then open DuckDB **read-only**. If anything is missing, 03 is
not done and this cell raises — we do not build the tables here.
"""
)

code(
    r"""
PROCESSED = PROJECT / "data" / "processed"
REQUIRED_CHART_TABLES = [
    "chart_admin_vs_instruction_by_sector",
    "chart_admin_share_trend",
    "chart_spend_by_function_by_year",
    "chart_admin_per_fte_by_state",
    "chart_admin_per_fte_by_state_top_bottom",
    "chart_tuition_vs_cpi",
    # REFRAME EXPANSION — new chart tables consumed by the N1-N4 charts below.
    "chart_tuition_longrun",
    "chart_spending_mix",
    "chart_staff_indexed",
    "chart_admin_faculty_ratio",
]
missing_files = [t for t in REQUIRED_CHART_TABLES if not (PROCESSED / f"{t}.parquet").exists()]
assert not missing_files, f"Stage-03 processed tables missing: {missing_files} — run 03-prepare first."

for pkg in ["higher_education_cost_v1.csv", "higher_education_cost_v1_codebook.md"]:
    assert (PROJECT / "export" / pkg).exists(), f"Stage-03 export missing: {pkg} — run 03-prepare first."

# 04 is read-only — never writes.
con = duckdb.connect(str(DB), read_only=True)

# Confirm the processed tables are registered in the DB and non-empty.
present = con.execute(
    "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'chart_%' ORDER BY table_name"
).df()["table_name"].tolist()
for t in REQUIRED_CHART_TABLES:
    assert t in present, f"{t} not in DuckDB — 03-prepare incomplete."
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    assert n > 0, f"{t} is empty."
    print(f"OK  {t:<42} rows={n}")
print("\nStage-03 gate satisfied — consuming chart_* tables read-only.")
"""
)

# ---------------------------------------------------------------------------
md(
    """
## 1 — Admin vs instruction spending per FTE, public vs private, 2012 → 2022  *(lead cut, slopegraph)*

The headline comparison, drawn as a **slopegraph** — the textbook replacement for
paired before/after bars. Each line is one **(sector × function)** series:
public-instruction, public-admin, private-instruction, private-admin. The LEFT
column is 2012, the RIGHT is 2022 (both mean per-FTE, constant 2022 $). The
slope of each line reads the direction and size of the decade change at a glance,
so the public-falls / private-rises divergence is immediate.

*Source: `chart_admin_vs_instruction_by_sector` (consumed read-only). Each row =
one sector×function line; periods = 2012 → 2022. Mean per 12-month FTE, constant
2022 $. "Admin" = IPEDS institutional_support. GASB vs FASB definitions differ —
treat public↔private as indicative.*

> **Data basis — two snapshots a decade apart, not an annual series.** Every
> 2012→2022 slopegraph here compares **two** IPEDS finance collection years:
> **FY 2011-12 (labeled "2012") and FY 2021-22 (labeled "2022")**. **FY 2011-12
> is the EARLIEST year ingested** — there is no pre-2012 finance data in this
> pipeline (the processed `chart_*` tables carry only years 2012 and 2022). So
> each line connects two points a decade apart; the slope reads the net decade
> change, not a year-by-year path. (The one annual series in this notebook is the
> CPI index line in chart 5b.)
"""
)

code(
    r"""
d1 = con.execute(
    "SELECT control, year, function, mean_per_fte_real2022 "
    "FROM chart_admin_vs_instruction_by_sector "
    "WHERE function IN ('instruction', 'institutional_support') "
    "ORDER BY control, function, year"
).df()
SECT = {"public": "Public", "private_np": "Private NP"}
FUNC = {"instruction": "instruction", "institutional_support": "admin"}
d1["series"] = (
    d1["control"].map(SECT) + " " + d1["function"].map(FUNC)
)
# One ROW per series, with the two periods as columns (slopegraph wants wide).
d1_wide = d1.pivot_table(index="series", columns="year",
                         values="mean_per_fte_real2022").reset_index()
d1_wide = d1_wide.rename(columns={2012: "y2012", 2022: "y2022"})
d1_wide = d1_wide[["series", "y2012", "y2022"]]
print(d1_wide.to_string(index=False))
# Confirm the series row order (pivot sorts alphabetically) so we know which
# palette color each line WOULD take by default, before we pin colors.
print("series row order:", d1_wide["series"].tolist())

# EDIT 1 — explicit per-line colors so the two PUBLIC lines read as a warm,
# complementary pair (gold + spice, both on the warm/right side of the brand
# ramp) and the two PRIVATE lines keep their original cool colors (navy + cyan).
# A full 4-key map is passed so nothing shifts on the palette cycle. Keys match
# the exact `series` labels built above (SECT + FUNC maps).
chart1_colors = {
    "Public instruction":     c("gold"),    # was aqua (cool) -> warm; complements admin
    "Public admin":           c("spice"),   # KEEP its current warm color
    "Private NP instruction": c("cyan"),    # unchanged (default palette color)
    "Private NP admin":       c("navy"),    # unchanged (default palette color)
}

cf.render_chart({
    "type": "slopegraph",
    "table": d1_wide,
    "label_col": "series",
    "period_cols": ["y2012", "y2022"],
    "period_labels": ["2012", "2022"],
    "value_fmt": (lambda v: f"${v:,.0f}"),
    "series_colors": chart1_colors,
    "title": "Admin vs instruction spending per FTE, by sector, 2012 \u2192 2022",
    "subtitle": "Mean per 12-month FTE student, constant 2022 $. Admin = IPEDS institutional support. "
                "Each line is one sector\u00d7function.",
})
"""
)

# ---------------------------------------------------------------------------
md(
    """
## 2 — Institutional-support (admin) share of core spending, by sector, 2012 → 2022  *(slopegraph)*

Rather than dollar levels, the **share** admin takes of core function spending
(instruction + research + public service + student services + institutional
support — the same denominator per sector), drawn as a **slopegraph** with one
line per sector (public, private nonprofit), 2012 → 2022. Shows whether the *mix*
tilted toward admin, independent of overall cost growth.

*Source: `chart_admin_share_trend` (consumed read-only). Each row = one sector
line; periods = 2012 → 2022. Mean institutional-support share across institutions,
per sector. Shares are within-sector (GASB vs FASB), so read the 2012→2022 move
within each sector rather than the public-vs-private gap. Units: % of core
spending.*
"""
)

code(
    r"""
d2 = con.execute(
    "SELECT control, year, mean_admin_share FROM chart_admin_share_trend ORDER BY control, year"
).df()
d2["series"] = d2["control"].map({"public": "Public", "private_np": "Private NP"})
d2["pct"] = (d2["mean_admin_share"] * 100)
d2_wide = d2.pivot_table(index="series", columns="year", values="pct").reset_index()
d2_wide = d2_wide.rename(columns={2012: "y2012", 2022: "y2022"})[["series", "y2012", "y2022"]]
print(d2_wide.to_string(index=False))

cf.render_chart({
    "type": "slopegraph",
    "table": d2_wide,
    "label_col": "series",
    "period_cols": ["y2012", "y2022"],
    "period_labels": ["2012", "2022"],
    "value_fmt": (lambda v: f"{v:.1f}%"),
    "title": "Admin share of core spending, by sector, 2012 \u2192 2022",
    "subtitle": "Mean institutional-support share of core functions per institution. "
                "Within-sector (GASB vs FASB). Admin = IPEDS institutional support only; "
                "function definitions below.",
})
"""
)

# ---------------------------------------------------------------------------
md(
    """
### IPEDS expense-function definitions  *(applies to charts 2 and 3)*

The category-breakdown charts (chart 2's admin *share*, and chart 3's per-function
slopegraphs) split spending into the IPEDS **expense-by-function** categories.
Plain-English definitions of each:

- **Instruction** — teaching activities: faculty salaries, departmental instruction, credit & non-credit courses.
- **Research** — activities organized to produce research, funded by external grants or institutional funds.
- **Public service** — non-instructional services to external groups (extension, community programs).
- **Academic support** — support for instruction/research: libraries, academic computing, museums, curriculum development, deans' offices.
- **Student services** — admissions, registrar, financial-aid administration, counseling, career services, student activities (NOT financial-aid dollars themselves).
- **Institutional support ("admin")** — day-to-day operational support: executive/governance, fiscal operations, HR, legal, public relations, general administration.

**⭐ In this project, "admin" = Institutional support ONLY** — *not* academic
support, *not* student services. Both of those are their own separate functions
above and are never folded into the admin figure.

*(GASB (public) and FASB (private nonprofit) define these functions slightly
differently, so public↔private comparisons are indicative, not exact; a function
is only compared across sectors where the design allows it — `academic_support`
is shown per sector only.)*
"""
)

# ---------------------------------------------------------------------------
md(
    """
## 3 — Spending per FTE by function, within each sector, 2012 → 2022  *(slopegraph, per sector)*

The full function breakdown per FTE (constant 2022 $) within each sector, so admin
sits in context next to instruction, research, student services, academic support,
and public service.

**Judgment call (per the brief):** this is 6 functions × 2 years × 2 sectors. One
combined slopegraph would be 12 lines and crowd badly, and — more importantly —
`academic_support` is only meaningful **within** a sector (never public-vs-private,
per design §1.2). So this stays **one slopegraph per sector** (6 function lines
each, 2012 → 2022). Each line's slope reads how that function's per-FTE dollars
moved over the decade.

*Source: `chart_spend_by_function_by_year` (consumed read-only). Each row = one
function line; periods = 2012 → 2022. Mean per 12-month FTE, constant 2022 $. One
chart per sector.*
"""
)

code(
    r"""
d3 = con.execute(
    "SELECT control, year, function, mean_per_fte_real2022 "
    "FROM chart_spend_by_function_by_year ORDER BY control, function, year"
).df()

FUNC_LABEL = {
    "instruction": "Instruction",
    "institutional_support": "Inst. support (admin)",
    "research": "Research",
    "student_services": "Student services",
    "academic_support": "Academic support",
    "public_service": "Public service",
}

for control, nice in [("public", "Public institutions"),
                      ("private_np", "Private nonprofit institutions")]:
    sub = d3[d3["control"] == control].copy()
    sub["series"] = sub["function"].map(FUNC_LABEL)
    wide = sub.pivot_table(index="series", columns="year",
                           values="mean_per_fte_real2022").reset_index()
    wide = wide.rename(columns={2012: "y2012", 2022: "y2022"})[["series", "y2012", "y2022"]]
    print(f"--- {nice} ---")
    print(wide.to_string(index=False))
    cf.render_chart({
        "type": "slopegraph",
        "table": wide,
        "label_col": "series",
        "period_cols": ["y2012", "y2022"],
        "period_labels": ["2012", "2022"],
        "value_fmt": (lambda v: f"${v:,.0f}"),
        # EDIT 2 — taller canvas so the 6 function endpoints spread out and the
        # template's down-only label de-overlap fires less often, keeping each
        # series label beside its own endpoint value (and separating the
        # research / academic-support pair). This is the ONLY config lever the
        # frozen slopegraph template exposes for label placement (see the
        # markdown note above chart 3 for the residual template limitation).
        "img_height": 1050,
        "title": f"Spending per FTE by function \u2014 {nice}, 2012 \u2192 2022",
        "subtitle": "Mean per 12-month FTE student, constant 2022 $. Each line is one function. "
                    "Function definitions below.",
    })
"""
)

# ---------------------------------------------------------------------------
md(
    """
> **Label-placement note (shared slopegraph template limitation — for the owner).**
> The taller canvas above spreads the endpoints enough that on the **2022 side**
> of both sectors every function label sits cleanly beside its own dollar value,
> and **Research reads clearly above Academic support** (the pair the owner
> flagged no longer overlaps there). **One residual remains on the private-nonprofit
> chart's 2012 side:** Research ($6,577) and Academic support ($5,770) are only
> ~$800 apart on a per-FTE scale, so their *endpoint values* still overprint and
> the Student-services label is pushed off its value.
>
> This cannot be fixed through project config. The frozen shared template
> (`shared/chart_templates.py::slopegraph`) draws each **endpoint value** at the
> dot's y-center with **no de-overlap**, while **series labels** get a separate
> **down-only** de-overlap in `_draw_side_labels` — and that helper sorts labels
> by endpoint y, so **reordering the dataframe rows has no effect**, and there is
> no config key to (i) nudge a single label up, (ii) co-move a value with its
> de-overlapped label, or (iii) set a per-series offset / minimum gap. `img_height`
> (applied here) is the only lever, and it resolves everything except two endpoints
> within one line-height of each other. **A shared-template change — e.g. a
> bidirectional/greedy label spreader, co-placing each value+label as one block, or
> a per-series `label_dy` / min-gap arg — would be required to fully fix the 2012-side
> private cluster.** Per the brief the template is NOT edited here; flagged for the
> owner to decide.
"""
)

# ---------------------------------------------------------------------------
md(
    """
## 4 — Biggest state moves in admin (institutional support) per FTE, 2012 → 2022

Where did admin-per-FTE rise or fall most across the decade? To keep this readable,
each sector shows only the **5 states where admin-per-FTE rose the most and the 5
where it fell the most** (top 5 + bottom 5 = **10 bars**), ranked by the 2012→2022
dollar change — **not** all ~100 states. The selection is done in `03-prepare`
(`chart_admin_per_fte_by_state_top_bottom`); this cell only consumes it. Public
institutions have near-universal state coverage; private-nonprofit coverage is
sparser (its extremes can be single-institution states), shown separately with a
"read with care" note.

*Source: `chart_admin_per_fte_by_state_top_bottom` (consumed read-only; top-5 +
bottom-5 states per sector by `admin_change`). Change in mean institutional-support
per 12-month FTE, constant 2022 $. States with few institutions are noisy.*
"""
)

code(
    r"""
# EDIT 3 (consume side) — read the 03 top-5 + bottom-5 table (10 states per
# sector), NOT the full ~100-row chart_admin_per_fte_by_state. No CREATE TABLE here.
d4 = con.execute(
    "SELECT stabbr, control, admin_2012, admin_2022, n_2012, n_2022, admin_change, band "
    "FROM chart_admin_per_fte_by_state_top_bottom ORDER BY control, admin_change"
).df()

for control, nice, note in [
    ("public", "public institutions", "Top 5 rising + bottom 5 falling. Near-universal state coverage."),
    ("private_np", "private nonprofit", "Top 5 rising + bottom 5 falling. Sparse coverage — read with care."),
]:
    sub = d4[d4["control"] == control].copy().sort_values("admin_change")
    sub["label"] = sub["admin_change"].apply(lambda v: f"${v:+,.0f}")
    print(f"--- {nice}: {len(sub)} states ({(sub['band']=='top').sum()} rising / "
          f"{(sub['band']=='bottom').sum()} falling) ---")
    print(sub[["stabbr", "band", "admin_change"]].to_string(index=False))
    img = cf._render_diverging_bars(
        {
            "table": sub[["stabbr", "admin_change", "label"]],
            "category_col": "stabbr",
            "value_col": "admin_change",
            "label_col": "label",
            "pos_color": c("spice"),
            "neg_color": c("teal"),
            "sort": True,
            # 10 bars (not ~100) — a short canvas keeps them from stretching.
            "img_height": 700,
            "title": f"Biggest state moves in admin spending per FTE, {nice}, 2012 → 2022",
            "subtitle": f"$ change in mean institutional support per 12-month FTE, constant 2022 $. {note}",
        },
        None,
    )
    show(img)
"""
)

# ---------------------------------------------------------------------------
md(
    """
## 5 — Published (sticker) tuition, 2012 → 2022, by sector  *(slopegraph, constant 2022 $)*

Did the real published price of college rise over the decade, and by how much per
sector? A **slopegraph** of mean IPEDS **sticker tuition & fees** in **constant
2022 dollars**, one line each for **public in-state**, **public out-of-state**, and
**private nonprofit**, 2012 → 2022. Because the figures are inflation-adjusted on
the same CPI-U All-Items basis as the finance charts, the slope reads *real*
tuition growth (above and beyond general inflation), not nominal.

> **Dollar basis:** uses the `*_real2022` columns from `chart_tuition_vs_cpi`
> (constant 2022 $, CPI-U All-Items deflated — 2012 nominal × 1.27466), **NOT** the
> `*_nominal` columns. This keeps tuition consistent with every other chart in the
> project.

*Source: `chart_tuition_vs_cpi` (consumed read-only; IPEDS IC_AY sticker tuition,
constant 2022 $, mean per institution; 2012 n=4,455, 2022 n=3,587). Each row = one
sector line; periods = 2012 → 2022.*
"""
)

code(
    r"""
dt = con.execute(
    "SELECT year, "
    "mean_tuition_public_in_state_real2022, mean_tuition_public_out_state_real2022, "
    "mean_tuition_private_real2022, "
    "mean_tuition_public_in_state_nominal, mean_tuition_public_out_state_nominal, "
    "mean_tuition_private_nominal, n_tuition_reported "
    "FROM chart_tuition_vs_cpi WHERE year IN (2012, 2022) ORDER BY year"
).df()
assert dt["mean_tuition_public_in_state_real2022"].notna().all(), "2012/2022 real tuition missing"

# Charted values = the real-2022-$ columns (NOT nominal).
SECTORS = [
    ("mean_tuition_public_in_state_real2022", "Public in-state"),
    ("mean_tuition_public_out_state_real2022", "Public out-of-state"),
    ("mean_tuition_private_real2022", "Private nonprofit"),
]
rows = []
for col, nice in SECTORS:
    rows.append({
        "series": nice,
        "y2012": float(dt[dt["year"] == 2012][col].iloc[0]),
        "y2022": float(dt[dt["year"] == 2022][col].iloc[0]),
    })
dt_wide = pd.DataFrame(rows)[["series", "y2012", "y2022"]]
print("Slopegraph input (constant 2022 $):")
print(dt_wide.to_string(index=False))

cf.render_chart({
    "type": "slopegraph",
    "table": dt_wide,
    "label_col": "series",
    "period_cols": ["y2012", "y2022"],
    "period_labels": ["2012", "2022"],
    "value_fmt": (lambda v: f"${v:,.0f}"),
    "title": "Published (sticker) tuition, 2012 \u2192 2022, by sector",
    "subtitle": "Mean IPEDS tuition & fees per institution, constant 2022 $ (CPI-U All-Items). "
                "2012 n=4,455, 2022 n=3,587.",
})

print("\nReal (constant 2022 $) vs nominal change, by sector:")
for col, nice in SECTORS:
    r12 = float(dt[dt["year"] == 2012][col].iloc[0])
    r22 = float(dt[dt["year"] == 2022][col].iloc[0])
    nom_col = col.replace("_real2022", "_nominal")
    n12 = float(dt[dt["year"] == 2012][nom_col].iloc[0])
    n22 = float(dt[dt["year"] == 2022][nom_col].iloc[0])
    print(f"  {nice:<20} real ${r12:,.0f} -> ${r22:,.0f} ({(r22/r12-1)*100:+.0f}% real)   "
          f"| nominal ${n12:,.0f} -> ${n22:,.0f} ({(n22/n12-1)*100:+.0f}% nominal)")
"""
)

# ---------------------------------------------------------------------------
md(
    """
## 5b — College tuition prices vs general inflation, 2012–2022  *(context)*

The same decade seen through CPI: two index lines (2012 = 100), the **CPI-U
college tuition & fees subindex** vs **CPI-U All Items**. Both CPI series are
complete annual 2012–2022 and give the year-by-year path alongside the two-point
IPEDS sticker trend above.

*Source: `chart_tuition_vs_cpi`. CPI-U NSA, 2012 = 100.*
"""
)

code(
    r"""
d5 = con.execute(
    "SELECT year, cpi_all_index_2012base, cpi_tuition_index_2012base "
    "FROM chart_tuition_vs_cpi ORDER BY year"
).df()

img = cf._render_line(
    {
        "table": d5[["year", "cpi_tuition_index_2012base", "cpi_all_index_2012base"]],
        "x_col": "year",
        "series": [
            {"col": "cpi_tuition_index_2012base", "label": "College tuition & fees (CPI subindex)", "color": c("spice")},
            {"col": "cpi_all_index_2012base", "label": "All items (CPI-U)", "color": c("gray")},
        ],
        "x_axis_label": "Year",
        "y_axis_label": "CPI index (2012 = 100)",
        "y_min": 95,
        "markers": True,
        "label_last": True,
        "x_tick_step": 2,
        "title": "College tuition prices vs general inflation, 2012\u20132022",
        "subtitle": "CPI-U index, 2012 = 100. Tuition & fees subindex vs All Items.",
    },
    None,
)
show(img)
"""
)

# ---------------------------------------------------------------------------
md(
    r"""
---

# ⭐ REFRAME — "big education" vs the inflation of other sectors

Everything above (charts 1–5b) is the **original admin-vs-classroom exploration**
— kept intact as a valued exploration record. The charts below are the **reframe**
(`SECTOR-COMPARISON-INVESTIGATION.md`): the project's new headline question is
**has the cost of higher education outpaced general inflation AND the other "big"
sectors** culture argues about — big pharma / healthcare, big oil / energy — plus
housing?

These consume the two chart-ready tables `03-prepare` built from the CPI-U sector
subindices (`chart_cpi_indexed`, `chart_cpi_pct_change`), read-only. No `chart_*`
table is built here. All annual-average CPI-U, NSA, 1979 → latest full year, each
sector re-indexed to 100 at **1979** (the floor set by the college-tuition
subindex, which begins Dec 1978). **Prior art:** this is the longer-window
extension of the AEI / Mark-Perry "Chart of the Century" — cited, not copied.

**Titles describe, they don't conclude** (per the workspace viz rule).
"""
)

code(
    r"""
# Confirm the reframe chart tables are present (03 built them), read-only.
for t in ["chart_cpi_indexed", "chart_cpi_pct_change"]:
    assert (PROCESSED / f"{t}.parquet").exists(), f"{t} missing — run 03-prepare first."
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    assert n > 0, f"{t} is empty."
    print(f"OK  {t:<24} rows={n}")
LATEST = int(con.execute("SELECT MAX(year) FROM chart_cpi_indexed").fetchone()[0])
print("latest full year in the CPI sector data:", LATEST)
"""
)

# ---------------------------------------------------------------------------
md(
    r"""
## R1 — "Why don't we ever talk about 'Big Education'?"  *(HEADLINE / lead chart, multi-line)*

The classic "which line is steepest" chart: every CPI-U sector re-indexed so
**1979 = 100**, plotted 1979 → latest. A line's height in any year is the
cumulative price change since 1979 (e.g. 400 = prices quadrupled). College
tuition & fees is the steepest line by a wide margin. Eight sectors on the common
1979 window (hospital services, which starts 1996, is excluded here).

> **⭐ Provocative title — intentional, owner-approved per-chart opt-in.** The
> workspace default is "titles describe, don't conclude," but this is the week's
> **lead / introduction chart for a controversial-tier project**, so the owner
> explicitly asked for a provocative headline here: **"Why don't we ever talk
> about 'Big Education'?"**. This is a deliberate exception for **R1 ONLY** — do
> NOT "fix" it back to a descriptive title, and do NOT make any other chart in
> this notebook (R2, R3, the diverging bar, the slopegraphs) provocative. The
> subtitle stays informative (source = BLS CPI-U, base year 1979, indexed to 100).

*Source: `chart_cpi_indexed` (consumed read-only; `in_headline` sectors only).
BLS CPI-U, U.S. city average, NSA, annual averages, 1979 = 100. The tuition
subindex tracks published (sticker) price, not net-of-aid.*

> **End-label de-overlap.** Near the right edge the medical-care cluster
> ("Medical care services" / "Medical care (all)" / "Prescription drugs") bunches
> together, so their direct end-of-line labels would overprint. The shared
> `line` template now spreads near-equal endpoint labels to a minimum vertical gap
> (a behavior-preserving fix — it only engages when labels actually collide), so
> every sector label reads cleanly beside its own line end.
"""
)

code(
    r"""
# Pivot the long indexed table to wide (one column per sector) for the line template.
d_idx = con.execute(
    "SELECT year, sector, index_1979base FROM chart_cpi_indexed "
    "WHERE in_headline ORDER BY year"
).df()
wide_idx = d_idx.pivot_table(index="year", columns="sector",
                             values="index_1979base").reset_index()

# Order the series by their latest-year value (steepest first) so the legend /
# end-labels read top-to-bottom in rank order; pin tuition to the brand spice.
order = (d_idx[d_idx["year"] == LATEST]
         .sort_values("index_1979base", ascending=False)["sector"].tolist())
SECTOR_COLORS = {
    "College tuition & fees": c("spice"),   # the headline line — warm, stands out
    "Medical care services":  c("navy"),
    "Medical care (all)":     c("teal"),
    "Prescription drugs":     c("aqua"),
    "Shelter":                c("gold"),
    "All items":              c("gray"),     # the baseline reference line
    "Energy":                 c("cyan"),
    "Gasoline":               c("brown_red"),
}
series = [{"col": s, "label": s, "color": SECTOR_COLORS.get(s, c("gray"))} for s in order]

img = cf._render_line(
    {
        "table": wide_idx[["year"] + order],
        "x_col": "year",
        "series": series,
        "x_axis_label": "Year",
        "y_axis_label": "Price index (1979 = 100)",
        "y_min": 100,
        "markers": False,
        "label_last": True,
        "legend": True,
        "x_tick_step": 5,
        # ⭐ Provocative LEAD-chart title — owner-approved per-chart exception to
        # the "titles describe, don't conclude" rule (R1 only; see markdown note).
        "title": "Why don\u2019t we ever talk about \u201CBig Education\u201D?",
        "subtitle": f"BLS CPI-U, U.S. city average, NSA, annual averages, 1979\u2013{LATEST}. "
                    f"1979 = 100. Higher line = larger cumulative price rise.",
    },
    None,
)
show(img)

print("Indexed values at", LATEST, "(1979 = 100), steepest first:")
print(d_idx[d_idx["year"] == LATEST].sort_values("index_1979base", ascending=False)
      [["sector", "index_1979base"]].round(1).to_string(index=False))
"""
)

# ---------------------------------------------------------------------------
md(
    r"""
## R2 — The "big" sectors head-to-head  *(reduced multi-line)*

The same chart stripped to the cultural "big pharma / big oil / big education"
cut: **college tuition** vs **healthcare** (medical care services) vs **energy**
(or gasoline) vs **All Items** — four clean lines, 1979 = 100. Easier to read
than the full eight-line headline and the version most likely to carry a post.

*Source: `chart_cpi_indexed` (consumed read-only; four sectors). BLS CPI-U, NSA,
1979 = 100.*
"""
)

code(
    r"""
BIG4 = ["College tuition & fees", "Medical care services", "Energy", "All items"]
d_big = con.execute(
    "SELECT year, sector, index_1979base FROM chart_cpi_indexed "
    "WHERE sector IN ('College tuition & fees','Medical care services','Energy','All items') "
    "ORDER BY year"
).df()
wide_big = d_big.pivot_table(index="year", columns="sector",
                             values="index_1979base").reset_index()
big_order = (d_big[d_big["year"] == LATEST]
             .sort_values("index_1979base", ascending=False)["sector"].tolist())
big_series = [{"col": s, "label": s, "color": SECTOR_COLORS.get(s, c("gray"))} for s in big_order]

img = cf._render_line(
    {
        "table": wide_big[["year"] + big_order],
        "x_col": "year",
        "series": big_series,
        "x_axis_label": "Year",
        "y_axis_label": "Price index (1979 = 100)",
        "y_min": 100,
        "markers": False,
        "label_last": True,
        "legend": True,
        "x_tick_step": 5,
        "title": "\u201CBig\u201D sectors head-to-head: tuition, healthcare, energy, all items",
        "subtitle": f"BLS CPI-U, U.S. city average, NSA, 1979\u2013{LATEST}. 1979 = 100. "
                    f"Education vs big healthcare vs big energy vs general inflation.",
    },
    None,
)
show(img)
"""
)

# ---------------------------------------------------------------------------
md(
    r"""
## R3 — the one-number bar, in TWO variants

The one-number companion to the headline line chart comes in two framings. The
owner picked **option "b" (the diverging bar) as the PRIMARY reframe**, and asked
to **keep option "a" (the total-% bar) in the notebook for comparison**. Both are
built below so the difference is obvious. **Only R1 carries the provocative title;
both bars here are DESCRIPTIVE.**

- **Option b — PRIMARY:** each sector relative to **All Items** (how much it
  out-ran / lagged general inflation). All Items = 0, tuition the largest positive
  bar. The "above the inflation line / below it" reading, which is the more
  interesting cut.
- **Option a — COMPARISON (kept):** each sector's **total** % increase since 1979,
  with All Items drawn as a **reference line** so you can still read who sits above
  vs below general inflation on the raw-growth scale.

### R3b (PRIMARY) — How much each sector out-ran general inflation since 1979  *(diverging bar, option "b")*

Every sector recentred on **All Items**: `pct_vs_allitems = (sector_index /
allitems_index − 1) × 100`. All Items is the **zero baseline** (its own distinct
colour, labelled as the reference); sectors that **beat** general inflation sit to
the right, sectors that **lagged** it to the left. College tuition & fees is the
largest positive bar by a wide margin; gasoline / energy land near or below zero.

**Colour rule (per the brief):** All Items gets its **own** distinct colour (the
reference / zero point). Every *actual* sector uses the standard diverging
above/below-zero colours — **college tuition is NOT given a unique highlight
colour here** (it stands out by length, not hue).

*Source: `chart_cpi_vs_allitems` (consumed read-only; `in_headline` sectors). BLS
CPI-U, NSA; each sector's cumulative price change recentred on All Items.*
"""
)

code(
    r"""
d_vs = con.execute(
    "SELECT sector, pct_vs_allitems, pct_vs_allitems_label, is_allitems "
    "FROM chart_cpi_vs_allitems WHERE in_headline ORDER BY pct_vs_allitems DESC"
).df()
print(d_vs.to_string(index=False))

# Colour rule: All Items (the zero/reference row) gets its OWN distinct colour via
# `highlight`; every actual sector takes the standard diverging above/below-zero
# colours (pos = teal_dark beat inflation, neg = spice lagged it). College tuition
# is deliberately NOT highlighted — it reads by bar length, not a unique hue.
img = cf._render_diverging_bars(
    {
        "table": d_vs[["sector", "pct_vs_allitems", "pct_vs_allitems_label"]],
        "category_col": "sector",
        "value_col": "pct_vs_allitems",
        "label_col": "pct_vs_allitems_label",
        "pos_color": c("teal_dark"),   # beat general inflation (right of zero)
        "neg_color": c("spice"),       # lagged general inflation (left of zero)
        "highlight": {"category": "All items", "color": c("gold"),
                      "annotation": "general inflation (reference = 0)"},
        "zero_label": "All items (general inflation) = 0",
        "sort": True,
        "img_height": 760,
        "title": f"How much each sector out-ran general inflation, 1979 \u2192 {LATEST}",
        "subtitle": "BLS CPI-U, U.S. city average, NSA. Each sector's cumulative price change "
                    "since 1979 vs All Items (All items = 0; right = beat inflation, left = lagged).",
    },
    None,
)
show(img)

nonref = d_vs[~d_vs["is_allitems"]].sort_values("pct_vs_allitems", ascending=False)
print("\nTop 3 sectors that beat general inflation most (pct vs All Items):")
print(nonref.head(3)[["sector", "pct_vs_allitems"]].to_string(index=False))
print("Bottom 3 (lagged / least out-ran general inflation):")
print(nonref.tail(3)[["sector", "pct_vs_allitems"]].to_string(index=False))
print(f"College tuition & fees vs All Items: "
      f"{float(nonref[nonref.sector=='College tuition & fees']['pct_vs_allitems'].iloc[0]):+.1f}%")
"""
)

md(
    r"""
### R3a (COMPARISON, kept) — Total price increase by sector since 1979, vs the inflation line  *(ranked bar, option "a")*

The original one-number framing, **kept for comparison** so the two cuts sit side
by side. Total **percent increase from 1979 to the latest full year** per sector,
ranked (tuition on top), with **All Items drawn as a dashed reference line** — so
you can read who sits **above vs below general inflation** without recentring the
scale. This is the AEI-style "here is the single number" companion; the diverging
R3b above is the same information recentred on that inflation line.

*Source: `chart_cpi_pct_change` (consumed read-only; `in_headline` sectors). BLS
CPI-U, NSA; `(index_latest / index_1979 − 1) × 100`. All Items reference value is
the All-Items row of the same table.*
"""
)

code(
    r"""
d_pct = con.execute(
    "SELECT sector, pct_change_since_1979, pct_label FROM chart_cpi_pct_change "
    "WHERE in_headline ORDER BY pct_change_since_1979 DESC"
).df()
print(d_pct.to_string(index=False))

# All Items total % change = the reference line (who's above vs below inflation).
all_items_pct = float(d_pct[d_pct["sector"] == "All items"]["pct_change_since_1979"].iloc[0])
print(f"\nAll Items reference line at +{all_items_pct:.0f}%")

img = cf._render_single_ranked_bars(
    {
        "table": d_pct,
        "category_col": "sector",
        "value_col": "pct_change_since_1979",
        "label_col": "pct_label",
        "bar_color": c("teal"),
        "highlight": {"category": "College tuition & fees", "color": c("spice")},
        # Option "a": draw All Items as a reference line so the chart reads
        # "who's above vs below the inflation line" on the raw-growth scale.
        "ref_line": {"value": all_items_pct, "color": c("gold"),
                     "label": f"All items (general inflation) +{all_items_pct:.0f}%"},
        "sort": "desc",
        "title": f"Total price increase by sector, 1979 \u2192 {LATEST} (vs the inflation line)",
        "subtitle": "BLS CPI-U, U.S. city average, NSA. Cumulative % change since 1979; dashed line = "
                    "All Items (general inflation). Comparison version of the diverging chart above.",
    },
    None,
)
show(img)
"""
)

# ===========================================================================
# REFRAME EXPANSION — new exploration charts (N1–N4) from Sources A–D
# ===========================================================================
md(
    r"""
---

# ⭐ REFRAME EXPANSION — deeper cuts from the four new sources

Everything above (charts 1–5b and R1–R3) is preserved unchanged. The charts below
(**N1–N4**) are the NEW exploration from the four sources ingested this pass:
the deep tuition history (NCES 330.10), the long spending-mix (Delta Cost Project
1987-2012 + raw-IPEDS tail), and the admin-vs-faculty headcount (IPEDS HR). They
consume the chart-ready tables `03-prepare` built — read-only; no `chart_*` table
is built here.

**ALL N-charts carry DESCRIPTIVE titles** (the one provocative title, "Big
Education", is reserved for the R1 lead only). They answer Suspicion 2 (is the
cost rise driven by administration?) **honestly** — the data says *non-
instructional* spending outgrew instruction, NOT "administrators alone exploded,"
and that nuance IS the finding.
"""
)

code(
    r"""
# Confirm the expansion chart tables are present (03 built them), read-only.
for t in ["chart_tuition_longrun", "chart_spending_mix", "chart_staff_indexed",
          "chart_admin_faculty_ratio"]:
    assert (PROCESSED / f"{t}.parquet").exists(), f"{t} missing — run 03-prepare first."
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    assert n > 0, f"{t} is empty."
    print(f"OK  {t:<28} rows={n}")
TUI_BASE = int(con.execute("SELECT MAX(base_year) FROM chart_tuition_longrun").fetchone()[0])
TUI_LAST = int(con.execute("SELECT MAX(year_start) FROM chart_tuition_longrun").fetchone()[0])
MIX_Y0 = int(con.execute("SELECT MIN(year) FROM chart_spending_mix").fetchone()[0])
MIX_Y1 = int(con.execute("SELECT MAX(year) FROM chart_spending_mix").fetchone()[0])
HR_Y0 = int(con.execute("SELECT MIN(year) FROM chart_staff_indexed").fetchone()[0])
HR_Y1 = int(con.execute("SELECT MAX(year) FROM chart_staff_indexed").fetchone()[0])
print(f"tuition {min(1963, TUI_LAST)}-{TUI_LAST} (constant {TUI_BASE}-$); "
      f"spending-mix {MIX_Y0}-{MIX_Y1}; HR {HR_Y0}-{HR_Y1}")
"""
)

# --------------------------------------------------------------------------- N1
md(
    r"""
## N1 — Published tuition & fees, 1963-64 → latest, constant dollars  *(deep skyrocket, multi-line)*

The long view of the owner thesis: real (inflation-adjusted) published
undergraduate tuition & fees since 1963-64, one line per control (all / public /
private), 4-year institutions, in constant NCES dollars. This is the decades-long
climb the CPI index chart (R1) implies, now in actual dollars.

*Source: `chart_tuition_longrun` (consumed read-only; constant-$ tuition&fees,
4-year, by control). NCES Digest Table 330.10. National averages, published
(sticker) price, not net-of-aid; constant dollars use CPI-U All-Items.*
"""
)

code(
    r"""
d_n1 = con.execute(
    "SELECT year_start, control, value_constant FROM chart_tuition_longrun "
    "WHERE level = '4-year' ORDER BY year_start"
).df()
wide_n1 = d_n1.pivot_table(index="year_start", columns="control",
                           values="value_constant").reset_index()
N1_COLORS = {"all": c("gold"), "public": c("teal"), "private": c("navy")}
N1_LABELS = {"all": "All institutions", "public": "Public", "private": "Private"}
order_n1 = ["private", "all", "public"]  # private highest -> public lowest at the right edge
series_n1 = [{"col": k, "label": N1_LABELS[k], "color": N1_COLORS[k]} for k in order_n1]

img = cf._render_line(
    {
        "table": wide_n1[["year_start"] + order_n1],
        "x_col": "year_start",
        "series": series_n1,
        "x_axis_label": "Academic year (start)",
        "y_axis_label": f"Tuition & fees (constant {TUI_BASE}-$)",
        "y_min": 0,
        "markers": False,
        "label_last": True,
        "legend": True,
        "x_tick_step": 10,
        "y_fmt": (lambda v: f"${v:,.0f}"),
        "title": f"Published undergraduate tuition & fees, 1963\u201364 to {TUI_LAST}\u2013{str(TUI_LAST+1)[-2:]}",
        "subtitle": f"NCES Digest Table 330.10. Constant {TUI_BASE}-{str(TUI_BASE+1)[-2:]} dollars "
                    f"(CPI-U All-Items); 4-year institutions by control. Published (sticker) price.",
    },
    None,
)
show(img)

pub = d_n1[d_n1.control == "public"].sort_values("year_start")
print(f"Public 4-yr constant-${TUI_BASE} tuition&fees: "
      f"1963 ${float(pub.iloc[0].value_constant):,.0f} -> {TUI_LAST} ${float(pub.iloc[-1].value_constant):,.0f} "
      f"({float(pub.iloc[-1].value_constant)/float(pub.iloc[0].value_constant):.1f}x real)")
"""
)

# --------------------------------------------------------------------------- N2
md(
    r"""
## N2 — Where the money goes: spending mix, 1987 → latest  *(multi-line share + slopegraph endpoints)*

The admin-driver question, answered HONESTLY. Two renders of the same
`chart_spending_mix` data (national SHARE of core functional spending): a
multi-line showing the full 1987→latest path, and a slopegraph of the 1987-vs-
latest endpoints (the owner's established slopegraph preference). The four
functions are **instruction** vs the three non-instructional ones
(**institutional support = admin**, **academic support**, **student services**).

**⭐ The honest story (read the slopes):** instruction's share FELL while the
NON-INSTRUCTIONAL functions rose — but **institutional support (admin) alone is
roughly FLAT**; the growth is in student services + academic support. So the
defensible headline is "non-instructional spending outgrew instruction," NOT
"administrators alone exploded." That institutional-support-is-flat nuance is
itself a finding.

*Source: `chart_spending_mix` (consumed read-only; national share by function).
NCES Delta Cost Project (1987-2012) + raw IPEDS Finance (2013+); **seam at 2012**;
"admin" = institutional support only; Delta is a derived product (Jaquette-Parra);
GASB isolates O&M while FASB distributes it.*
"""
)

code(
    r"""
d_n2 = con.execute(
    "SELECT year, function, share FROM chart_spending_mix ORDER BY year"
).df()
FUNC_N2 = {
    "instruction": "Instruction",
    "institutional_support": "Inst. support (admin)",
    "academic_support": "Academic support",
    "student_services": "Student services",
}
F2_COLORS = {
    "Instruction": c("teal"),
    "Inst. support (admin)": c("spice"),
    "Academic support": c("navy"),
    "Student services": c("gold"),
}
d_n2["label"] = d_n2["function"].map(FUNC_N2)
d_n2["pct"] = d_n2["share"] * 100
wide_n2 = d_n2.pivot_table(index="year", columns="label", values="pct").reset_index()
order_n2 = ["Instruction", "Inst. support (admin)", "Academic support", "Student services"]
series_n2 = [{"col": s, "label": s, "color": F2_COLORS[s]} for s in order_n2]

img = cf._render_line(
    {
        "table": wide_n2[["year"] + order_n2],
        "x_col": "year",
        "series": series_n2,
        "x_axis_label": "Year",
        "y_axis_label": "Share of core spending (%)",
        "y_min": 0,
        "markers": False,
        "label_last": True,
        "legend": True,
        "x_tick_step": 5,
        "y_fmt": (lambda v: f"{v:.0f}%"),
        "title": f"Share of core spending by function, {MIX_Y0} to {MIX_Y1}",
        "subtitle": f"NCES Delta Cost Project ({MIX_Y0}\u20132012) + IPEDS Finance (2013\u2013{MIX_Y1}), "
                    f"national. Admin = institutional support only. Seam at 2012.",
    },
    None,
)
show(img)
"""
)

code(
    r"""
# Same data as an endpoints slopegraph (1987 vs latest) — the owner's preferred cut.
ends_n2 = d_n2[d_n2.year.isin([MIX_Y0, MIX_Y1])]
wide_slope = ends_n2.pivot_table(index="label", columns="year", values="pct").reset_index()
wide_slope = wide_slope.rename(columns={MIX_Y0: "y0", MIX_Y1: "y1"})[["label", "y0", "y1"]]
print(wide_slope.to_string(index=False))

cf.render_chart({
    "type": "slopegraph",
    "table": wide_slope,
    "label_col": "label",
    "period_cols": ["y0", "y1"],
    "period_labels": [str(MIX_Y0), str(MIX_Y1)],
    "value_fmt": (lambda v: f"{v:.1f}%"),
    "series_colors": F2_COLORS,
    "title": f"Core spending mix by function, {MIX_Y0} vs {MIX_Y1}",
    "subtitle": "Share of core functional spending, national. Instruction fell; non-instructional rose "
                "\u2014 but institutional support (admin) alone is roughly flat.",
})

# Honest-nuance printout.
piv = d_n2.pivot_table(index="year", columns="label", values="pct")
noninstr0 = piv.loc[MIX_Y0, ["Inst. support (admin)", "Academic support", "Student services"]].sum()
noninstr1 = piv.loc[MIX_Y1, ["Inst. support (admin)", "Academic support", "Student services"]].sum()
print(f"\nInstruction share : {piv.loc[MIX_Y0,'Instruction']:.1f}% -> {piv.loc[MIX_Y1,'Instruction']:.1f}%")
print(f"Non-instructional : {noninstr0:.1f}% -> {noninstr1:.1f}%")
print(f"Admin ALONE       : {piv.loc[MIX_Y0,'Inst. support (admin)']:.1f}% -> "
      f"{piv.loc[MIX_Y1,'Inst. support (admin)']:.1f}%  (roughly flat \u2014 the nuance)")
"""
)

# --------------------------------------------------------------------------- N3
md(
    r"""
## N3 — Administrators, faculty, and enrollment since 2013, indexed  *(multi-line, 2013 = 100)*

The intuitive "bloat" proxy: headcount of **administrators** (IPEDS HR Management)
vs **faculty** (Instructional staff) vs **enrollment** (12-month FTE), each indexed
to 100 at 2013. If the admin line pulls above faculty and enrollment, administrative
staffing grew faster than the teaching workforce and the student body.

> **⭐ Footnote (required):** IPEDS replaced its staff occupational categories in
> 2012-13 (2010-SOC); this series is shown **from 2013 only** and is NOT comparable
> to earlier IPEDS staff categories.

*Source: `chart_staff_indexed` (consumed read-only). IPEDS Human Resources
(Management vs Instructional staff headcount) + 12-month FTE; 2013 = 100.*
"""
)

code(
    r"""
d_n3 = con.execute(
    "SELECT year, series, index_base FROM chart_staff_indexed ORDER BY year"
).df()
N3_LABELS = {"admin": "Administrators (Management)", "faculty": "Faculty (Instructional)",
             "enrollment": "Enrollment (12-mo FTE)"}
N3_COLORS = {"Administrators (Management)": c("spice"), "Faculty (Instructional)": c("teal"),
             "Enrollment (12-mo FTE)": c("gray")}
d_n3["label"] = d_n3["series"].map(N3_LABELS)
wide_n3 = d_n3.pivot_table(index="year", columns="label", values="index_base").reset_index()
order_n3 = ["Administrators (Management)", "Faculty (Instructional)", "Enrollment (12-mo FTE)"]
series_n3 = [{"col": s, "label": s, "color": N3_COLORS[s]} for s in order_n3]

img = cf._render_line(
    {
        "table": wide_n3[["year"] + order_n3],
        "x_col": "year",
        "series": series_n3,
        "x_axis_label": "Year",
        "y_axis_label": "Index (2013 = 100)",
        "markers": True,
        "label_last": True,
        "legend": True,
        "x_tick_step": 3,
        "y_fmt": (lambda v: f"{v:.0f}"),
        "title": f"Administrator, faculty, and enrollment growth since 2013 (indexed)",
        "subtitle": "IPEDS Human Resources + 12-month FTE, national; 2013 = 100. IPEDS replaced staff "
                    "occupational categories in 2012-13 (2010-SOC) \u2014 series shown from 2013 only.",
    },
    None,
)
show(img)

ip3 = d_n3.pivot_table(index="year", columns="series", values="index_base")
yl = int(ip3.index.max())
print(f"At {yl} (2013=100): admin={ip3.loc[yl,'admin']:.1f}, faculty={ip3.loc[yl,'faculty']:.1f}, "
      f"enrollment={ip3.loc[yl,'enrollment']:.1f}")
"""
)

# --------------------------------------------------------------------------- N4
md(
    r"""
## N4 — Administrators per 100 faculty, 2013 vs latest  *(then-vs-now, lollipop)*

The quotable one-number companion to N3: how many administrators (Management) per
100 faculty (Instructional staff), first HR year vs latest. Same 2012-13 SOC-break
footnote.

*Source: `chart_admin_faculty_ratio` (consumed read-only). IPEDS Human Resources.*
"""
)

code(
    r"""
d_n4 = con.execute(
    "SELECT year, admin_per_100_faculty FROM chart_admin_faculty_ratio ORDER BY year"
).df()
d_n4["label"] = d_n4["year"].astype(str)
print(d_n4.to_string(index=False))

img = cf._render_lollipop(
    {
        "table": d_n4[["label", "admin_per_100_faculty"]],
        "category_col": "label",
        "value_col": "admin_per_100_faculty",
        "value_fmt": (lambda v: f"{v:.1f}"),
        "dot_color": c("spice"),
        "legend": False,
        "title": "Administrators per 100 faculty, 2013 vs latest",
        "subtitle": "IPEDS Human Resources (Management staff per 100 instructional staff). "
                    "Series clean from 2012-13 (2010-SOC categories) only.",
    },
    None,
)
show(img)
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Takeaways to review (framing only — nothing published yet)

Every 2012-vs-2022 before/after comparison here is now a **slopegraph** (charts
1, 2, 3, 5) — the two-point structure reads more directly as a slope than as
paired/grouped bars. Chart 4 (a single 2012→2022 *change* value per state) stays
diverging bars, and chart 5b (a full annual CPI series) stays a line — neither is
a two-point before/after.

- **Levels (chart 1, slopegraph):** instruction per FTE still sits above admin per
  FTE in both sectors. The slopes show the divergence — public lines are roughly
  flat / edge down in constant-$ terms, private-nonprofit lines rise.
- **Mix (chart 2, slopegraph):** the admin *share* of core spending rose in both
  sectors (public ~21% → ~24%; private ~30% → ~31%) — both slopes point up, the
  public one more steeply.
- **By function (chart 3, per-sector slopegraphs):** admin sits below instruction
  in both sectors; academic support and student services are the other sizeable
  non-instruction buckets. Kept per-sector (not one 12-line chart) because
  academic_support is only comparable within a sector.
- **By state (chart 4, diverging bars):** admin-per-FTE change is very uneven
  across states; a handful of small-n states dominate the extremes.
- **Sticker tuition (chart 5, slopegraph, constant 2022 $):** real published
  tuition & fees rose in all three sectors 2012 → 2022, now on the same
  CPI-U-All-Items 2022-dollar basis as the finance charts (uses the `*_real2022`
  columns, not nominal).
- **Prices (chart 5b, line):** the CPI tuition subindex ran ahead of All-Items CPI
  across 2012–2022.

These are exploratory framings for owner review — **not** final social charts. No
`06-viz-social` / web rendering is built in this stage.

---

### ⭐ REFRAME takeaways (the new headline direction)

- **R1 (headline, indexed line — the provocative LEAD):** titled "Why don't we
  ever talk about 'Big Education'?" (the one owner-approved provocative title; see
  the note above the chart). With every sector re-indexed to 100 at 1979,
  **college tuition & fees is the steepest line by a wide margin** — it reaches
  ~**1,477** by the latest year (≈ **+1,377%** since 1979), far above the next
  sector, **medical care services ~942 (+842%)**, and roughly **3×** general
  inflation (All items ~443, +343%). This directly makes "big education" visible.
  End-of-line labels in the medical-care cluster are now de-overlapped (shared
  `line` template fix) so each reads beside its own line end.
- **R2 (big-4 cut):** the cultural "big pharma / big oil / big education" framing
  reads cleanly in four lines — tuition rises fastest, big healthcare second,
  energy/gasoline track near or below general inflation.
- **R3b (PRIMARY — diverging vs All Items, option "b"):** recentred on general
  inflation, **tuition out-ran All Items by ~+233%** (the largest positive bar),
  medical-care services ~+112%, medical-care (all) ~+94% — the top three above the
  inflation line. Below it: **gasoline ~−10% and energy ~−4%** (they LAGGED general
  inflation), with shelter ~+36% just above. All Items sits at 0 in its own colour;
  tuition reads by length, not a highlight colour.
- **R3a (COMPARISON — ranked total %, option "a", kept):** the same sectors on the
  raw-growth scale with All Items drawn as a dashed reference line (+343%). Tuition
  on top; the reference line makes "above vs below general inflation" readable
  without recentring. (Hospital services shows a larger raw % but is correctly
  excluded from the 1979 headline — its CPI series only starts 1996.)
- These confirm the reframe's Suspicion 1 (relative inflation) is a strong,
  defensible headline. Suspicion 2 (is the driver admin vs instruction) is now
  built below (N1–N4) from the Delta Cost Project + IPEDS HR ingest.

---

### ⭐ REFRAME EXPANSION takeaways (N1–N4 — the new honest findings for owner review)

The four new sources answer the "how dramatic is the long tuition climb?" and
"is the driver administration?" questions. Headline numbers (exact figures printed
by the cells above):

- **N1 — deep tuition skyrocket (NCES 330.10, constant dollars):** real published
  tuition & fees roughly **4× since 1963-64** at public 4-year institutions
  (≈ $2,440 → ≈ $9,900 in constant 2023-$). Private rose even higher in level.
  This is the decades-long climb R1 shows as a CPI index, now in actual dollars —
  dramatic, and the longest view in the project.
- **N2 — spending mix, 1987 → latest (Delta + IPEDS tail) — ⭐ the load-bearing
  honest nuance:** instruction's SHARE of core spending **FELL** (~49% → ~43%)
  while **non-instructional** spending (student services + academic support +
  institutional support) **ROSE** (~33% → ~37%). **BUT institutional support
  (admin) ALONE is roughly FLAT** (~15% → ~15%); the growth is in **student
  services** (+~2.5 pp) and **academic support** (+~1.7 pp). So the defensible
  story is **"non-instructional spending outgrew instruction," NOT "administrators
  alone exploded."** The admin-is-flat result is itself a finding and is weaker
  than the owner's prior — say so, don't overclaim.
- **N3 — admin vs faculty vs enrollment, indexed (IPEDS HR, 2013 = 100):** on the
  HEADCOUNT proxy, administrators (Management) **did** outpace both — by the latest
  year admin ≈ **108** vs faculty ≈ **95** vs enrollment ≈ **88** (2013 = 100). So
  the intuitive "more administrators per student/teacher" reading holds on
  headcount even though admin SPENDING share (N2) is flat — a genuine, more
  quotable complement, NOT a contradiction (headcount ≠ share of dollars).
- **N4 — administrators per 100 faculty, then vs now:** ≈ **17.6 (2013) → ≈ 20.1
  (latest)** — the same N3 story as a single quotable ratio.
- **Caveats to carry (do NOT drop):** N1 is national-average sticker price, not
  net-of-aid, constant-$ via CPI-U All-Items. N2 has a **2012 seam** (Delta ends
  2011-12, raw IPEDS after), Delta is a derived product (Jaquette-Parra), and
  "admin" = institutional support only. N3/N4 are clean only from **2012-13**
  (the 2010-SOC category break) — no pre-2012 comparison.
- **For the owner to pick (NOT pre-picked here):** candidate additional social
  charts are N1 (deep tuition line), N2 (spending-mix slopegraph or line — honestly
  framed), and N3 (admin-vs-faculty-vs-enrollment indexed). The honest framing of
  N2 is a feature: it is more credible precisely because it does not overclaim.
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Cleanup

DuckDB is single-writer; close the read-only connection so no lock lingers.
"""
)

code(
    """
con.close()
print("DuckDB connection closed.")
"""
)

# ---------------------------------------------------------------------------
nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}

out = Path("notebooks/04-viz.ipynb")
nbf.write(nb, str(out))
print("Wrote", out, "with", len(cells), "cells")
