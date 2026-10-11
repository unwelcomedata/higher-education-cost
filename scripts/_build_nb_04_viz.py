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
