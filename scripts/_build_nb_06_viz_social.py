"""Build notebooks/06-viz-social.ipynb for higher-education-cost via nbformat.

STAGE 06-viz-social — PUBLICATION renders of the 4 OWNER-SELECTED charts from the
04-viz exploration. This notebook CONSUMES the chart-ready `chart_*` processed
tables that 03-prepare produced; it opens DuckDB **read-only** and closes it in a
`## Cleanup` cell. It does NOT build any chart data (that is 03's job) and it does
NOT touch the 04-viz exploration charts.

Run from the project root with the project venv:
    .venv/bin/python scripts/_build_nb_06_viz_social.py
    .venv/bin/python -m nbconvert --to notebook --execute --inplace notebooks/06-viz-social.ipynb

RENDERING ENGINE — the shared Pillow chart factory, not matplotlib. matplotlib on
this project's .venv (Python 3.14) RecursionErrors on any figure draw, so — exactly
as 04-viz does — every chart is built with the shared Pillow factory at ../../shared.
This is the SAME engine the 04-viz reframe charts used, so the social versions
cannot drift from exploration.

TWO-TARGET RENDERING (the workspace standard). Each of the 4 charts is rendered
TWICE from ONE base config:
  - social: twitter_landscape 1600x900, full chrome (title/subtitle/source/@watermark)
            -> outputs/social/
  - web:    web preset 1664x936, web_mode=True (drops title/subtitle/source, keeps
            ONLY the @unwelcomedata watermark) -> outputs/web/
A direct-builder helper is used because render_chart() only exports to
outputs/social; the web target is built via the factory builder fn and saved to
outputs/web manually (the presidential-readability / unemployment / pokemon pattern).

THE 4 OWNER-SELECTED CHARTS (ported from scripts/_build_nb_04_viz.py: R1, R3b,
N1, N2 — same data/column mappings so they cannot drift from exploration):
  1. R1  -> 01_big_education_indexed.png    (LEAD, PROVOCATIVE title — owner opt-in)
  2. R3b -> 02_outran_inflation_diverging.png (descriptive; All Items own color)
  3. N1  -> 03_tuition_since_1963.png        (descriptive; constant 2023-$)
  4. N2  -> 04_spending_mix.png              (descriptive; HONEST framing)
Charts the owner did NOT select (R2, R3a, N3, N4) stay exploration-only in 04-viz.
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
    r"""
# 06 — Viz (social + web) · higher-education-cost

**Publication-ready renders of the 4 OWNER-SELECTED charts** from the `04-viz`
exploration. The owner reviewed `04-viz` and picked exactly these four to carry
the week's "big education" story — this notebook renders only those, nothing more.

**Which 4, and why they were chosen** (the rest — R2, R3a, N3, N4 — stay
exploration-only in `04-viz`):

| # | 04-viz id | file | title style |
|---|-----------|------|-------------|
| 1 | **R1** | `01_big_education_indexed.png` | **PROVOCATIVE (lead)** |
| 2 | **R3b** | `02_outran_inflation_diverging.png` | descriptive |
| 3 | **N1** | `03_tuition_since_1963.png` | descriptive |
| 4 | **N2** | `04_spending_mix.png` | descriptive, **honest framing** |

**⭐ R1 keeps its provocative title — explicit owner decision.** The workspace
default is "titles describe, don't conclude," but this is a *controversial-tier*
project and R1 is the week's **lead / introduction** chart, so the owner
explicitly asked for the provocative headline **"We say 'Big Pharma' and 'Big
Oil.' Why not 'Big Education'?"** on R1 ONLY. The other three carry plain descriptive titles.

**⭐ N2 is framed HONESTLY.** The data says instruction's *share* fell while
*non-instructional* spending (student services + academic support + institutional
support) rose — **but institutional support (admin) ALONE is roughly flat**. So
the chart supports "**non-instructional spending outgrew instruction**," NOT
"administrators alone exploded." Not overclaiming is the point (serious tier).

**Stage gate.** This is the publication stage. It runs AFTER `03-prepare` (which
built the chart-ready `chart_*` tables and the `export/` package) and AFTER the
`04-viz` exploration the owner reviewed. It opens DuckDB **read-only** and never
builds chart data here.

**Rendering engine.** matplotlib RecursionErrors on this venv (Python 3.14), so
every chart uses the **shared Pillow factory** (`../../shared`) — the SAME engine
`04-viz` used, so these social renders cannot drift from the exploration.

**Two-target rendering.** Each chart renders TWICE from one config: **social**
(`twitter_landscape` 1600×900, full chrome) → `outputs/social/`, and **web**
(`web` 1664×936, `web_mode=True`, chrome dropped, watermark kept) → `outputs/web/`.
"""
)

code(
    r"""
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
SOCIAL = PROJECT / "outputs" / "social"
WEB = PROJECT / "outputs" / "web"
SOCIAL.mkdir(parents=True, exist_ok=True)
WEB.mkdir(parents=True, exist_ok=True)

# 06 is read-only — it consumes 03's chart_* tables; it never writes to the DB.
con = duckdb.connect(str(DB), read_only=True)


def render_dual(base_config: dict, filename: str):
    # Render ONE chart to BOTH targets from a single base config.
    # social = twitter_landscape 1600x900 + full chrome; web = web preset 1664x936
    # + web_mode (title/subtitle/source dropped, @unwelcomedata watermark kept).
    # Built via the factory builder fn directly so each target saves to its own
    # dir (render_chart()'s own export only writes outputs/social). The social
    # version is display()'d inline so the notebook IS the record of what shipped.
    ctype = base_config["type"]
    builder = cf._CHART_TYPES[ctype]

    social_cfg = {**base_config, "preset": "twitter_landscape", "web_mode": False}
    img_social = builder(social_cfg, con)
    p_social = SOCIAL / f"{filename}.png"
    img_social.save(p_social)

    web_cfg = {**base_config, "preset": "web", "web_mode": True,
               "title": "", "subtitle": None, "source": None}
    img_web = builder(web_cfg, con)
    p_web = WEB / f"{filename}.png"
    img_web.save(p_web)

    print(f"{filename}: social {img_social.size} -> {p_social.name} | web {img_web.size} -> {p_web.name}")
    display(img_social)
    return p_social, p_web


LATEST = int(con.execute("SELECT MAX(year) FROM chart_cpi_indexed").fetchone()[0])
print("Project:", PROJECT.name, "| latest CPI year:", LATEST)
"""
)

# ---------------------------------------------------------------------------
md(
    r"""
## 1 — R1 (LEAD, provocative): "We say 'Big Pharma' and 'Big Oil.' Why not 'Big Education'?"

The classic "which line is steepest" chart: every CPI-U sector re-indexed so
**1979 = 100**, 1979 → latest. A line's height in any year is the cumulative price
change since 1979 (e.g. 400 = prices quadrupled). **College tuition & fees is the
steepest line by a wide margin** (~1,477 by {latest}, ≈ +1,377% since 1979), far
above medical-care services (~942) and roughly 3× general inflation (All items
~443). Eight sectors on the common 1979 window.

Ported verbatim from `04-viz` R1 (same `chart_cpi_indexed` headline sectors, same
color map, same steepest-first ordering) so the social render cannot drift from the
exploration.

> **⭐ Provocative title — intentional, owner-approved, R1 ONLY.** Do NOT make this
> descriptive; it is the week's provocative introduction to a controversial-tier
> project. The subtitle stays informative (source, base year, indexing).

> **⭐ End-label de-overlap — the #1 acceptance criterion.** Near the right edge two
> clusters bunch: (a) medical-care services / medical-care (all) / prescription
> drugs, and (b) all items / energy / gasoline. The shared `line` template's
> end-label spreader was strengthened to a legible, symmetric, iterative spreader
> (full-line-height minimum gap, centered so a cluster opens around its own
> centroid, short muted leader lines when a label is nudged off its line end). It
> ONLY increases separation, so it never regresses other charts.
"""
)

code(
    r"""
# Ported from 04-viz R1 — headline sectors only, read-only.
d_idx = con.execute(
    "SELECT year, sector, index_1979base FROM chart_cpi_indexed "
    "WHERE in_headline ORDER BY year"
).df()
wide_idx = d_idx.pivot_table(index="year", columns="sector",
                             values="index_1979base").reset_index()

# Order the series by their latest-year value (steepest first) so the end-labels
# read top-to-bottom in rank order; pin tuition to the brand spice.
order = (d_idx[d_idx["year"] == LATEST]
         .sort_values("index_1979base", ascending=False)["sector"].tolist())
SECTOR_COLORS = {
    "College tuition & fees": c("spice"),   # the headline line — warm, stands out
    "Medical care services":  c("navy"),
    "Medical care (all)":     c("teal"),
    "Prescription drugs":     c("aqua"),
    "Shelter":                c("gold"),
    "All items":              c("gray"),    # the baseline reference line
    "Energy":                 c("cyan"),
    "Gasoline":               c("brown_red"),
}
series = [{"col": s, "label": s, "color": SECTOR_COLORS.get(s, c("gray"))} for s in order]

render_dual({
    "type": "line",
    "table": wide_idx[["year"] + order],
    "x_col": "year",
    "series": series,
    "x_axis_label": "",
    "y_axis_label": "Price index (1979 = 100)",
    "y_min": 100,
    "markers": False,
    "label_last": True,
    "legend": False,
    "x_tick_step": 5,
    # ⭐ Provocative LEAD-chart title — owner-approved per-chart exception (R1 only).
    "title": "We say \u201CBig Pharma\u201D and \u201CBig Oil.\u201D Why not \u201CBig Education\u201D?",
    "subtitle": f"BLS CPI-U, U.S. city average, NSA, annual averages, 1979\u2013{LATEST}. "
                f"1979 = 100; higher line = larger cumulative price rise. "
                f"Window starts 1979 because the BLS college-tuition subindex begins Dec 1978.",
    "source": "BLS CPI-U (U.S. city average, NSA, annual averages)",
}, "01_big_education_indexed")

print("Indexed values at", LATEST, "(1979 = 100), steepest first:")
print(d_idx[d_idx["year"] == LATEST].sort_values("index_1979base", ascending=False)
      [["sector", "index_1979base"]].round(1).to_string(index=False))
"""
)

md(
    r"""
**Info-preservation (web mode strips the chrome).** On the web variant the title,
subtitle, and source are dropped, so the facts that live ONLY in the chrome must be
carried in the page prose later: **source = BLS CPI-U** (U.S. city average, NSA,
annual averages); **base year 1979 = 100**; the y-axis unit is a **price index**
(a line at 400 means prices quadrupled since 1979); window **1979 → {LATEST}**. The
sector names survive (direct end-labels), as does the steepest-line read.
"""
)

# ---------------------------------------------------------------------------
md(
    r"""
## 2 — R3b (descriptive): How much each sector out-ran general inflation since 1979

The one-number companion to the lead line, recentred on **All Items**:
`pct_vs_allitems = (sector_index / allitems_index − 1) × 100`. All Items is the
**zero baseline**; sectors that **beat** general inflation sit to the right, those
that **lagged** it to the left. **College tuition & fees is the largest positive bar
(~+233%)**; medical-care services ~+112%; **gasoline (~−10%) and energy (~−4%)
actually LAGGED** general inflation.

Ported verbatim from `04-viz` R3b (same `chart_cpi_vs_allitems` headline rows).

> **⭐ Colour rule (owner).** All Items gets its OWN distinct colour (the reference /
> zero point). Every *actual* sector uses the standard diverging above/below-zero
> colours — **college tuition is NOT given a unique highlight colour here**; it
> stands out by bar length, not hue. Descriptive title (not provocative).
"""
)

code(
    r"""
# Ported from 04-viz R3b — headline sectors, read-only.
d_vs = con.execute(
    "SELECT sector, pct_vs_allitems, pct_vs_allitems_label, is_allitems "
    "FROM chart_cpi_vs_allitems WHERE in_headline ORDER BY pct_vs_allitems DESC"
).df()
print(d_vs.to_string(index=False))

render_dual({
    "type": "diverging_bars",
    "table": d_vs[["sector", "pct_vs_allitems", "pct_vs_allitems_label"]],
    "category_col": "sector",
    "value_col": "pct_vs_allitems",
    "label_col": "pct_vs_allitems_label",
    "pos_color": c("teal_dark"),   # beat general inflation (right of zero)
    "neg_color": c("spice"),       # lagged general inflation (left of zero)
    # All Items (the zero/reference row) gets its OWN distinct colour; tuition is
    # deliberately NOT highlighted (reads by bar length).
    "highlight": {"category": "All items", "color": c("gold"),
                  "annotation": "general inflation (reference = 0)"},
    "zero_label": "All items (general inflation) = 0",
    "sort": True,
    "img_height": 760,
    "title": f"How much each sector out-ran general inflation, 1979 \u2192 {LATEST}",
    "subtitle": "Each sector's cumulative price change since 1979 vs All Items "
                "(All items = 0; right = beat inflation, left = lagged).",
    "source": "BLS CPI-U (U.S. city average, NSA)",
}, "02_outran_inflation_diverging")
"""
)

md(
    r"""
**Info-preservation (web mode strips the chrome).** Carry in page prose: **source =
BLS CPI-U**; the window **1979 → {LATEST}**; the metric = **cumulative price change
relative to All Items (general inflation)**, so **All Items = 0** and a bar's length
is "percentage points it out-ran (right) or lagged (left) general inflation." The
per-bar % labels and the "All items = 0" zero label survive on the chart itself.
"""
)

# ---------------------------------------------------------------------------
md(
    r"""
## 3 — N1 (descriptive): Published tuition & fees, 1963-64 → latest, constant dollars

The long view of the thesis in *actual dollars*: real (inflation-adjusted) published
undergraduate tuition & fees since 1963-64, one line per control (all / public /
private), 4-year institutions, constant NCES dollars. **Public 4-year roughly
quadrupled in real terms** (~$2,442 → ~$9,872 constant 2023-$, ≈4×). This is the
decades-long climb the R1 index implies, now in dollars.

Ported verbatim from `04-viz` N1 (same `chart_tuition_longrun` 4-year rows, same
multi-line-by-control shape, same colors/order). The end-label spreader applies here
too if the three control lines bunch at the right edge.

> Descriptive title. Published (sticker) price, NOT net-of-aid.
"""
)

code(
    r"""
# Ported from 04-viz N1 — 4-year, by control, constant dollars, read-only.
TUI_BASE = int(con.execute("SELECT MAX(base_year) FROM chart_tuition_longrun").fetchone()[0])
TUI_LAST = int(con.execute("SELECT MAX(year_start) FROM chart_tuition_longrun").fetchone()[0])
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

render_dual({
    "type": "line",
    "table": wide_n1[["year_start"] + order_n1],
    "x_col": "year_start",
    "series": series_n1,
    "x_axis_label": "Academic year (start)",
    "y_axis_label": f"Tuition & fees (constant {TUI_BASE}-$)",
    "y_min": 0,
    "markers": False,
    "label_last": True,
    "legend": False,
    "x_tick_step": 10,
    "y_fmt": (lambda v: f"${v:,.0f}"),
    "title": f"Published undergraduate tuition & fees, 1963\u201364 to {TUI_LAST}\u2013{str(TUI_LAST+1)[-2:]}",
    "subtitle": f"Constant {TUI_BASE}-{str(TUI_BASE+1)[-2:]} dollars (CPI-U All-Items); 4-year "
                f"institutions by control. Published (sticker) price.",
    "source": "NCES Digest of Education Statistics, Table 330.10",
}, "03_tuition_since_1963")

pub = d_n1[d_n1.control == "public"].sort_values("year_start")
print(f"Public 4-yr constant-${TUI_BASE} tuition&fees: "
      f"1963 ${float(pub.iloc[0].value_constant):,.0f} -> {TUI_LAST} ${float(pub.iloc[-1].value_constant):,.0f} "
      f"({float(pub.iloc[-1].value_constant)/float(pub.iloc[0].value_constant):.1f}x real)")
"""
)

md(
    r"""
**Info-preservation (web mode strips the chrome).** Carry in page prose: **source =
NCES Digest Table 330.10**; the **constant-dollar basis** (CPI-U All-Items,
constant 2023-$) — this is the load-bearing fact, because the chart is inflation-
adjusted, so the ≈4× climb is REAL growth, not nominal; **4-year institutions**,
**published (sticker) price, not net-of-aid**. The control labels (All / Public /
Private) and the $ axis survive on the chart.
"""
)

# ---------------------------------------------------------------------------
md(
    r"""
## 4 — N2 (descriptive, HONEST): Where the money goes — spending mix, 1987 → latest

The admin-driver question, answered **honestly**. National **share** of core
functional spending over time: **instruction** vs the three non-instructional
functions (**institutional support = admin**, **academic support**,
**student services**).

**⭐ The honest story (read the slopes):** instruction's share **FELL**
(~48.8% → 43.1%) while **non-instructional** spending **ROSE** (~32.5% → 37.4%) —
**but institutional support (admin) ALONE is roughly FLAT (~14.7% → 15.3%, ~15%)**;
the growth is in student services + academic support. So the defensible headline is
"**non-instructional spending outgrew instruction**," NOT "administrators alone
exploded." That admin-is-flat nuance is itself the finding, and the subtitle says so.

Ported verbatim from `04-viz` N2 — the **slopegraph of 1987-vs-latest endpoints**
(the owner's established slopegraph preference), same `chart_spending_mix` data,
same four functions and colors.

> Descriptive title. Serious-tier caveat (compact in the subtitle): Delta Cost
> Project (1987-2012) + IPEDS finance tail, **seam at 2012**; "admin" = institutional
> support only.
"""
)

code(
    r"""
# Ported from 04-viz N2 — the 1987-vs-latest endpoints slopegraph, read-only.
MIX_Y0 = int(con.execute("SELECT MIN(year) FROM chart_spending_mix").fetchone()[0])
MIX_Y1 = int(con.execute("SELECT MAX(year) FROM chart_spending_mix").fetchone()[0])
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
ends_n2 = d_n2[d_n2.year.isin([MIX_Y0, MIX_Y1])]
wide_slope = ends_n2.pivot_table(index="label", columns="year", values="pct").reset_index()
wide_slope = wide_slope.rename(columns={MIX_Y0: "y0", MIX_Y1: "y1"})[["label", "y0", "y1"]]
print(wide_slope.to_string(index=False))

render_dual({
    "type": "slopegraph",
    "table": wide_slope,
    "label_col": "label",
    "period_cols": ["y0", "y1"],
    "period_labels": [str(MIX_Y0), str(MIX_Y1)],
    "value_fmt": (lambda v: f"{v:.1f}%"),
    "series_colors": F2_COLORS,
    "title": f"Where the money goes: core spending mix, {MIX_Y0} \u2192 {MIX_Y1}",
    "subtitle": "Share of core functional spending, national. Instruction fell; non-instructional "
                "rose \u2014 but institutional support (admin) alone is roughly flat. "
                "Delta Cost Project + IPEDS finance tail; seam at 2012.",
    "source": "NCES Delta Cost Project (1987\u20132012) + IPEDS Finance (2013+)",
}, "04_spending_mix")

# Honest-nuance printout (auditable).
piv = d_n2.pivot_table(index="year", columns="label", values="pct")
noninstr = ["Inst. support (admin)", "Academic support", "Student services"]
print(f"\nInstruction share : {piv.loc[MIX_Y0,'Instruction']:.1f}% -> {piv.loc[MIX_Y1,'Instruction']:.1f}%")
print(f"Non-instructional : {piv.loc[MIX_Y0,noninstr].sum():.1f}% -> {piv.loc[MIX_Y1,noninstr].sum():.1f}%")
print(f"Admin ALONE       : {piv.loc[MIX_Y0,'Inst. support (admin)']:.1f}% -> "
      f"{piv.loc[MIX_Y1,'Inst. support (admin)']:.1f}%  (roughly flat \u2014 the nuance)")
"""
)

md(
    r"""
**Info-preservation (web mode strips the chrome).** Carry in page prose: **source =
NCES Delta Cost Project (1987-2012) + IPEDS Finance (2013+)**, with the **2012 seam**
and "**admin = institutional support only**" caveats; and — most important — the
**honest framing itself**: "non-instructional spending outgrew instruction, but
admin alone is roughly flat (~15%)." That framing lives in the subtitle, so if the
subtitle is dropped it MUST be restated above the chart on the page; otherwise the
bare slopegraph could be misread as "admin exploded," which the data does not say.
The function labels and the 1987/latest endpoint % values survive on the chart.
"""
)

# ---------------------------------------------------------------------------
md(
    r"""
## Canonical record — what shipped and why

- **These 4 charts are the owner-selected social candidates** from the `04-viz`
  exploration (R1, R3b, N1, N2). The charts the owner did NOT pick — R2 (big-4 cut),
  R3a (ranked-total comparison), N3 (admin vs faculty headcount), N4 (admins per 100
  faculty) — remain **exploration-only** in `04-viz` and are deliberately NOT
  rendered here.
- **R1 keeps its provocative lead title** ("Why don't we ever talk about 'Big
  Education'?") by **explicit owner decision** — a per-chart opt-in exception to the
  describe-don't-conclude rule, because R1 is the week's provocative introduction to
  a controversial-tier project. R3b / N1 / N2 all carry plain descriptive titles.
- **N2 is framed honestly:** instruction's share fell (~48.8%→43.1%) while
  non-instructional spending rose (~32.5%→37.4%), but **institutional support (admin)
  alone is roughly flat (~15%)**. The chart + subtitle support "non-instructional
  outgrew instruction," not "administrators alone exploded." Not overclaiming is the
  serious-tier point.
- **Two-target rendering:** each chart is rendered twice from one config — a
  **social** PNG (`outputs/social/`, 1600×900, full chrome) and a **web** PNG
  (`outputs/web/`, 1664×936, `web_mode=True`, chrome dropped except the
  `@unwelcomedata` watermark). The per-chart info-preservation notes above record
  the facts that live ONLY in the chrome, so a later Pages page can carry them in
  prose.
- **Nothing is published here** — this stage only produces the 8 PNGs; release
  curation, validation, and publishing happen later.
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
print("DuckDB connection closed. 06-viz-social complete: 4 social + 4 web PNGs.")
"""
)

# ---------------------------------------------------------------------------
nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}

out = Path("notebooks/06-viz-social.ipynb")
nbf.write(nb, str(out))
print("Wrote", out, "with", len(cells), "cells")
