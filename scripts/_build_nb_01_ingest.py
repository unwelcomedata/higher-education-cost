"""Build notebooks/01-ingest.ipynb for higher-education-cost via nbformat.

Run from the project root with the project venv:
    .venv/bin/python scripts/_build_nb_01_ingest.py

Produces the canonical-record ingest notebook: one markdown cell per source
naming it, its confirmed URL, auth notes, and the GASB/FASB split, followed by
a code cell that calls the src/ helper and shows a representative result.
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
# 01 — Ingest · higher-education-cost

**Goal of this stage:** pull the raw source files for "how the cost of college
has changed over time, and where the money goes (admin vs classroom)" into
`data/raw/` **verbatim**, and load them into DuckDB as `*_raw` tables. No
cleaning or transformation happens here — that is the `02-clean` stage.

**Serious tier → authoritative U.S. federal / primary sources only.** All three
sources below are public-domain U.S. federal government works.

Three sources (each confirmed live **2026-09-30**; see per-source cells):

1. **IPEDS (NCES)** — tuition (sticker), finance (expenses by function), and
   enrollment, pulled for **two collection years, 2011-12 and 2021-22**, so a
   decade-long over-time comparison is possible.
2. **College Scorecard (U.S. Dept. of Education)** — modern net price, cost of
   attendance, completion, and earnings, per institution.
3. **BLS CPI-U** — All-Items and college-tuition-subindex price series for
   real-dollar adjustment.

Raw files land in `data/raw/` (gitignored — never committed). Provenance for
every table is recorded in the DuckDB `_sources` table.
"""
)

code(
    """
import io
import os
import sys
from pathlib import Path

# Resolve the project root (folder containing config.yaml) and make src importable.
PROJECT = Path.cwd()
while not (PROJECT / "config.yaml").exists() and PROJECT != PROJECT.parent:
    PROJECT = PROJECT.parent
os.chdir(PROJECT)
sys.path.insert(0, str(PROJECT))

from src.ingest import (
    load_config,
    download_ipeds_survey,
    read_ipeds_zip,
    ingest_scorecard,
    fetch_bls_series,
    raw_path,
)
from src.clean_quality import get_connection, load_to_duckdb, register_source, get_sources

cfg = load_config("config.yaml")
con = get_connection(cfg)   # opens/creates data/project.duckdb (single-writer!)
RETRIEVED = "2026-09-30"
print("Project:", cfg["project_name"])
print("DuckDB :", cfg["settings"]["duckdb_file"])
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Source 1 — IPEDS (NCES) · tuition, finance, enrollment

**Publisher:** National Center for Education Statistics (NCES), U.S. Dept. of
Education. **License:** public domain (U.S. federal government work).
**Auth:** none — no API key required.

**Download pattern (confirmed 2026-09-30):** the IPEDS Data Center serves each
survey component, each collection year, as a zipped CSV at a stable URL:

```
https://nces.ed.gov/ipeds/datacenter/data/<SURVEY_FILE>.zip
```

`download_ipeds_survey()` fetches the ZIP verbatim into
`data/raw/ipeds/<SURVEY_FILE>.zip`; `read_ipeds_zip()` loads the CSV inside for
inspection / DuckDB registration only (the ZIP on disk is the untouched raw
artifact).

**Years pulled:** `2012` (2011-12 collection) and `2022` (2021-22 collection) —
a full decade, enough for the over-time story without pulling every year.

**Survey files and what each becomes:**

| IPEDS file | Contents | DuckDB table |
|---|---|---|
| `HD2022` / `HD2012` | Institutional Characteristics header — state, sector, level, Carnegie class | `ipeds_hd_2022_raw` / `ipeds_hd_2012_raw` |
| `IC2022_AY` / `IC2012_AY` | Charges — published tuition & required fees (sticker price) | `ipeds_charges_2022_raw` / `ipeds_charges_2012_raw` |
| `F2122_F1A` / `F1112_F1A` | **Finance — GASB (public)** expenses by function | `ipeds_finance_gasb_2022_raw` / `ipeds_finance_gasb_2012_raw` |
| `F2122_F2` / `F1112_F2` | **Finance — FASB (private nonprofit)** expenses by function | `ipeds_finance_fasb_2022_raw` / `ipeds_finance_fasb_2012_raw` |
| `EFFY2022` / `EFFY2012` | 12-month unduplicated enrollment (for per-FTE normalization) | `ipeds_enrollment_2022_raw` / `ipeds_enrollment_2012_raw` |

> **⭐ CRITICAL METHODOLOGY HAZARD — the GASB/FASB split.** The IPEDS Finance
> survey is split by accounting standard: **GASB** (`*_F1A`) for public
> institutions and **FASB** (`*_F2`) for private nonprofits. The two use
> **different expense-function line items** and do **NOT map 1:1** — the
> "instruction vs institutional support" categories are named differently and
> defined differently. They are kept as **separate raw tables** and must never
> be summed or compared without an explicit harmonization step (in `02-clean`).
> This is the central "admin vs classroom" data trap for this project.
"""
)

code(
    r"""
# Map each IPEDS survey file -> the raw DuckDB table it lands in.
IPEDS_TABLES = {
    "HD2022":    "ipeds_hd_2022_raw",
    "HD2012":    "ipeds_hd_2012_raw",
    "IC2022_AY": "ipeds_charges_2022_raw",
    "IC2012_AY": "ipeds_charges_2012_raw",
    "F2122_F1A": "ipeds_finance_gasb_2022_raw",
    "F1112_F1A": "ipeds_finance_gasb_2012_raw",
    "F2122_F2":  "ipeds_finance_fasb_2022_raw",
    "F1112_F2":  "ipeds_finance_fasb_2012_raw",
    "EFFY2022":  "ipeds_enrollment_2022_raw",
    "EFFY2012":  "ipeds_enrollment_2012_raw",
}

ipeds_shapes = {}
for survey_file, table in IPEDS_TABLES.items():
    zip_path = download_ipeds_survey(survey_file, cfg)   # verbatim -> data/raw/ipeds/
    df = read_ipeds_zip(zip_path)                        # load CSV for registration
    load_to_duckdb(df, table, con)                       # raw table, no transform
    ipeds_shapes[table] = df.shape
    print(f"{survey_file:>10}  ->  {table:<32}  rows={df.shape[0]:>7,}  cols={df.shape[1]}")
"""
)

md(
    r"""
### ⚠️ Fix — IC2012_AY parsed one column off (all-"R" UNITID / tuition)

**The bug (found during the 03-prepare / 04-viz build):** in the first ingest,
`ipeds_charges_2012_raw` came out with **every `UNITID` and every tuition value
as the literal string `"R"`**, so 2012 sticker tuition was unusable (and so was
`charges_clean` for year 2012). The 2022 charges table (`ipeds_charges_2022_raw`)
was fine. The core admin-vs-classroom finance story never depended on this file;
this fix is purely to restore the 2012 tuition dollars for a 2012→2022 sticker-
tuition trend.

**Root cause — a trailing comma + a header/row column-count mismatch, NOT a
wrong file.** The base `IC2012_AY.zip` and its single CSV `ic2012_ay.csv` are the
correct files (no `_rv` revised variant was needed). The problem is in the file's
shape:

- `ic2012_ay.csv` **header has 268 column names** (its last name even carries a
  trailing space, `"CMP3GTD "`), but **every data row has 269 fields** — the rows
  end in a trailing comma, producing one extra, unnamed, empty field.
- When fields > header names, pandas' default C parser **silently promotes the
  first column to the row index**, shifting every labeled column one position to
  the left. So `UNITID` received `XTUIT1`'s value (the `"R"` imputation flag),
  `XTUIT1` received the real tuition, `TUITION1` received the next `"R"` flag, and
  so on down the row — exactly the all-`"R"` symptom.
- IPEDS interleaves imputation-flag columns (`X`-prefixed, holding `R`/`A`/`Y`)
  with the data columns, which is why the shifted values were all `"R"`.

**Why 2012 broke but 2022 didn't:** `ic2022_ay.csv` has **235 header names and
235 fields per row** — no trailing comma, no mismatch — so it parsed with correct
alignment. Only the 2012 file ships the trailing comma.

**The fix:** `read_ipeds_zip()` now reads with **`index_col=False`**, which forces
pandas to keep column 0 (`UNITID`) as data and drop the unnamed trailing empty
field. This repairs 2012 and is a no-op for 2022 (verified below). The raw ZIP on
disk is untouched — the trailing comma is still there verbatim; we just parse it
correctly.

The cell below **re-ingests `IC2012_AY` through the fixed `read_ipeds_zip()`**
and overwrites `ipeds_charges_2012_raw` with correctly-aligned data.
"""
)

code(
    r"""
# Re-ingest the IC2012 charges file through the fixed read_ipeds_zip (index_col=False).
# The raw ZIP already on disk is reused verbatim (no re-download needed); we only
# re-parse and overwrite the malformed raw table.
ic2012_zip = raw_path(cfg, "ipeds/IC2012_AY.zip")
df_ic2012 = read_ipeds_zip(ic2012_zip)
load_to_duckdb(df_ic2012, "ipeds_charges_2012_raw", con)

# Confirm the shift is gone: UNITID is now a real integer and TUITION1 a dollar value.
print("ipeds_charges_2012_raw re-parsed shape:", df_ic2012.shape)
print("Representative fixed rows (UNITID / XTUIT1 flag / TUITION1 dollars):")
print(
    con.execute(
        "SELECT UNITID, XTUIT1, TUITION1, XFEE1, FEE1 FROM ipeds_charges_2012_raw LIMIT 5"
    ).df().to_string(index=False)
)
n2012 = con.execute("SELECT COUNT(*) FROM ipeds_charges_2012_raw").fetchone()[0]
n_bad = con.execute(
    "SELECT COUNT(*) FROM ipeds_charges_2012_raw WHERE TRY_CAST(UNITID AS BIGINT) IS NULL"
).fetchone()[0]
print(f"\nrows = {n2012:,}   non-numeric UNITIDs remaining = {n_bad}  (expect 0)")
"""
)

md(
    """
### Representative peek — IPEDS sticker price (Charges) and the finance split

A quick look confirms the raw tables loaded and shows the GASB vs FASB
column-naming difference (the reason they stay separate).
"""
)

code(
    """
# Sticker-price charges table — UNITID keys to the HD header; TUITION2/FEE2 etc.
print("Charges 2022 columns (first 25):")
print(con.execute("SELECT * FROM ipeds_charges_2022_raw LIMIT 0").df().columns.tolist()[:25])
con.execute("SELECT * FROM ipeds_charges_2022_raw LIMIT 3").df()
"""
)

code(
    """
# GASB (public) vs FASB (private) finance — note the different function columns.
gasb_cols = con.execute("SELECT * FROM ipeds_finance_gasb_2022_raw LIMIT 0").df().columns.tolist()
fasb_cols = con.execute("SELECT * FROM ipeds_finance_fasb_2022_raw LIMIT 0").df().columns.tolist()
print(f"GASB (F1A) column count: {len(gasb_cols)}  e.g. {gasb_cols[:12]}")
print(f"FASB (F2)  column count: {len(fasb_cols)}  e.g. {fasb_cols[:12]}")
print("\\nGASB row count:", con.execute("SELECT COUNT(*) FROM ipeds_finance_gasb_2022_raw").fetchone()[0])
print("FASB row count:", con.execute("SELECT COUNT(*) FROM ipeds_finance_fasb_2022_raw").fetchone()[0])
"""
)

md(
    """
### Register IPEDS provenance

One `_sources` row per raw table, carrying the methodology and series-break
notes from `SOURCES.md` — especially the GASB/FASB accounting split and the
fact that IPEDS survey definitions have changed across the decade, so the 2012
and 2022 tables are not always perfectly comparable line-for-line.
"""
)

code(
    r"""
IPEDS_URL_TMPL = "https://nces.ed.gov/ipeds/datacenter/data/{file}.zip"
LICENSE = "Public domain (U.S. federal government work)"

# Per-component descriptions for the notes field.
IPEDS_NOTES = {
    "ipeds_hd_2022_raw": ("IPEDS Institutional Characteristics header 2021-22 — institution "
                          "directory: state (STABBR), sector, level, Carnegie class. Keys other "
                          "IPEDS tables via UNITID."),
    "ipeds_hd_2012_raw": "IPEDS Institutional Characteristics header 2011-12 (directory; UNITID key).",
    "ipeds_charges_2022_raw": ("IPEDS Charges (IC academic-year) 2021-22 — published tuition & "
                               "required fees (sticker price), by residency."),
    "ipeds_charges_2012_raw": "IPEDS Charges (IC academic-year) 2011-12 — published tuition & fees.",
    "ipeds_finance_gasb_2022_raw": ("IPEDS Finance GASB (F1A) FY2021-22 — expenses by function for "
                                    "PUBLIC institutions (GASB accounting)."),
    "ipeds_finance_gasb_2012_raw": "IPEDS Finance GASB (F1A) FY2011-12 — public-institution expenses by function.",
    "ipeds_finance_fasb_2022_raw": ("IPEDS Finance FASB (F2) FY2021-22 — expenses by function for "
                                    "PRIVATE NONPROFIT institutions (FASB accounting)."),
    "ipeds_finance_fasb_2012_raw": "IPEDS Finance FASB (F2) FY2011-12 — private-nonprofit expenses by function.",
    "ipeds_enrollment_2022_raw": "IPEDS EFFY 2021-22 — 12-month unduplicated enrollment (for per-FTE normalization).",
    "ipeds_enrollment_2012_raw": "IPEDS EFFY 2011-12 — 12-month unduplicated enrollment.",
}

FINANCE_METHOD = ("Finance survey split by accounting standard: GASB (F1A) = public institutions, "
                  "FASB (F2) = private nonprofit. Expense-function categories differ between the two "
                  "standards and do NOT map 1:1; kept as separate raw tables.")
FINANCE_BREAKS = ("GASB vs FASB are not directly comparable (different expense-function definitions). "
                  "Additionally, IPEDS Finance definitions have shifted over time — treat FY2011-12 and "
                  "FY2021-22 as separate series that require harmonization before comparison.")
GENERAL_BREAKS = ("IPEDS survey definitions have changed across collection years; 2011-12 vs 2021-22 "
                  "figures may not be perfectly comparable line-for-line.")

for survey_file, table in IPEDS_TABLES.items():
    is_finance = "finance" in table
    register_source(
        con,
        table=table,
        name=f"IPEDS {survey_file} (NCES)",
        url=IPEDS_URL_TMPL.format(file=survey_file),
        license=LICENSE,
        notes=IPEDS_NOTES[table],
        retrieved=RETRIEVED,
        methodology=(FINANCE_METHOD if is_finance
                     else "IPEDS complete data file; per-survey, per-year zipped CSV keyed by UNITID."),
        series_breaks=(FINANCE_BREAKS if is_finance else GENERAL_BREAKS),
    )
print("Registered", len(IPEDS_TABLES), "IPEDS sources.")
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Source 2 — College Scorecard · net price, cost, completion, earnings

**Publisher:** U.S. Department of Education. **License:** public domain.
**Auth:** none.

**URL (confirmed 2026-09-30):**
`https://ed-public-download.scorecard.network/downloads/Most-Recent-Cohorts-Institution_05192025.zip`

> The historical bulk host `ed-public-download.app.cloud.gov/downloads/CollegeScorecard_Raw_Data.zip`
> now returns **404**. The current host was resolved from the data.ed.gov CKAN
> package listing (`college-scorecard-all-data-files`) and is
> `ed-public-download.scorecard.network`. This ingest uses the **"Most Recent
> Institution-Level Data"** file — one CSV covering every Title IV institution's
> latest cohort (net price, cost of attendance, completion rate, earnings) — the
> right scope for the ingest layer. The full multi-year raw archive
> (`College_Scorecard_Raw_Data_05192025.zip`) is documented in `config.yaml`
> and can be pulled later if a per-year Scorecard series is needed.

`ingest_scorecard()` downloads the ZIP verbatim into
`data/raw/scorecard/` and returns the CSV inside → `scorecard_raw`.
"""
)

code(
    """
scorecard_zip, df_sc = ingest_scorecard(cfg)
load_to_duckdb(df_sc, "scorecard_raw", con)
print("Saved raw ZIP  :", scorecard_zip)
print("scorecard_raw  : rows =", f"{df_sc.shape[0]:,}", " cols =", df_sc.shape[1])

# Representative cost columns (Scorecard uses coded names; NPT4 = net price, COSTT4 = cost of attendance).
cost_cols = [c for c in df_sc.columns if c.startswith(("NPT4", "COSTT4", "TUITION", "C150", "MD_EARN"))]
print("\\nRepresentative cost/outcome columns present:", cost_cols[:15])
con.execute(
    "SELECT INSTNM, STABBR, CONTROL, NPT4_PUB, NPT4_PRIV, COSTT4_A FROM scorecard_raw LIMIT 5"
).df()
"""
)

code(
    r"""
register_source(
    con,
    table="scorecard_raw",
    name="College Scorecard — Most Recent Institution-Level Data",
    url=cfg["sources"]["scorecard"]["url"],
    license="Public domain (U.S. federal government work)",
    notes=("U.S. Dept. of Education College Scorecard, most-recent cohort per Title IV institution. "
           "Fields: net price (NPT4_*), cost of attendance (COSTT4_*), completion (C150_*), "
           "median earnings (MD_EARN_*). Net price != sticker price — report both explicitly."),
    retrieved=RETRIEVED,
    methodology=("Institution-level, most-recent-cohort snapshot. Bulk ZIP from the "
                 "ed-public-download.scorecard.network host (moved from the retired "
                 "app.cloud.gov host)."),
    series_breaks=("Scorecard field definitions and coverage have changed over cohorts; net-price "
                   "fields are robust from ~2009 onward. This file is a single latest-cohort snapshot, "
                   "not a time series."),
)
print("Registered scorecard_raw.")
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Source 3 — BLS CPI-U · inflation adjustment

**Publisher:** U.S. Bureau of Labor Statistics. **License:** public domain.

> **Blocker note & workaround:** the BLS flat-file host
> `https://download.bls.gov/pub/time.series/cu/` returns a **403 Akamai block
> page** to automated GETs (confirmed 2026-09-30, even with a full browser
> header set). CPI-U is therefore pulled from the **BLS public timeseries API**
> (`https://api.bls.gov/publicAPI/v2/timeseries/data/`), which is **keyless**
> for modest use (25 requests/day, ≤10 years per request). An optional
> `BLS_API_KEY` in the **gitignored `.env`** raises the limits but is **not
> required** here.

**Series pulled** (2000–2024, annual averages included):
- `CUUR0000SA0` — CPI-U, **All Items**, U.S. city average, NSA (real-dollar deflator).
- `CUUR0000SEEB01` — CPI-U, **college tuition & fees** subindex (lets us compare
  tuition inflation against general inflation — the core "cost over time" hook).

The API is keyless-limited to ≤10 years per request, so the 2000–2024 span is
fetched in two calls and concatenated. The raw long-format payload is saved to
`data/raw/cpi_u/cpi_u_raw.csv` and loaded as `cpi_u_raw`.
"""
)

code(
    r"""
from src.ingest import raw_path
import pandas as pd

cpi_cfg = cfg["sources"]["cpi_u"]
series_ids = list(cpi_cfg["series"].keys())
api_key = os.environ.get("BLS_API_KEY")  # optional; from gitignored .env if set

# Keyless API allows <=10 years/request -> split 2000-2024 into two windows.
frames = []
for (sy, ey) in [(2000, 2009), (2010, 2024)]:
    frames.append(fetch_bls_series(series_ids, sy, ey, annual=True, api_key=api_key))
df_cpi = pd.concat(frames, ignore_index=True)

# Save the raw payload verbatim to data/raw (this IS the raw artifact for BLS).
cpi_dest = raw_path(cfg, "cpi_u/cpi_u_raw.csv")
df_cpi.to_csv(cpi_dest, index=False)

load_to_duckdb(df_cpi, "cpi_u_raw", con)
print("Saved raw CSV :", cpi_dest)
print("cpi_u_raw     : rows =", f"{df_cpi.shape[0]:,}", " cols =", df_cpi.shape[1])
print("Series present:", con.execute("SELECT DISTINCT series_id FROM cpi_u_raw").df()["series_id"].tolist())

# Representative rows: annual averages (period M13) for both series, recent years.
con.execute(
    "SELECT series_id, year, period, period_name, value FROM cpi_u_raw "
    "WHERE period = 'M13' AND year IN ('2012','2022') ORDER BY series_id, year"
).df()
"""
)

code(
    r"""
register_source(
    con,
    table="cpi_u_raw",
    name="BLS CPI-U (All Items + college tuition subindex)",
    url=cpi_cfg["api_url"],
    license="Public domain (U.S. federal government work)",
    notes=("BLS Consumer Price Index for All Urban Consumers. Series CUUR0000SA0 (All Items, NSA) "
           "for real-dollar adjustment and CUUR0000SEEB01 (college tuition & fees subindex). "
           "Long format: series_id, year, period (M01-M12 monthly, M13 annual avg), value. "
           "Fetched via the BLS public API because download.bls.gov flat files return HTTP 403."),
    retrieved=RETRIEVED,
    methodology=("BLS public timeseries API v2 (keyless). Monthly index values plus M13 annual "
                 "averages, 2000-2024, U.S. city average, not seasonally adjusted."),
    series_breaks=("CPI-U reference base is 1982-84=100. NSA used (do not mix with seasonally "
                   "adjusted series). Index rebasing/methodology revisions apply per BLS documentation."),
)
print("Registered cpi_u_raw.")
"""
)

# ---------------------------------------------------------------------------
md(
    r"""
## Source 3b (REFRAME) — BLS CPI-U **sector subindices** · the "big education" relative-inflation set

> **Why this source exists — the project reframe.** The project's new headline
> question is: has the **cost of higher education outpaced general inflation and
> the other sectors culture labels "big"** (big pharma / healthcare, big oil /
> energy) plus housing? The canonical way to answer it is to pull one **CPI-U
> subindex per sector**, re-index each to 100 in a common base year, and plot the
> lines — "which line is steepest." College tuition is reliably the steepest.
> See `artifacts/SECTOR-COMPARISON-INVESTIGATION.md` §1 for the full design.

**This is ingestion of a NEW data source (the sector subindices), so it belongs
here in `01-ingest`.** All series are **CPI-U, U.S. city average, NOT seasonally
adjusted** (the `CUUR0000…` prefix = CPI-**U** / area 0000 / **U**nadjusted).
They are pulled with the same keyless `fetch_bls_series()` used above.

**Series pulled** (series ID → human name → earliest BLS data):

| BLS series ID | Human name | Earliest |
|---|---|---|
| `CUUR0000SA0` | All Items (the general-inflation baseline) | 1913 |
| `CUUR0000SEEB01` | **College tuition & fees** ⭐ | **Dec 1978** |
| `CUUR0000SAM` | Medical care (all) | 1935 |
| `CUUR0000SAM2` | Medical care services (big-healthcare line) | 1956 |
| `CUUR0000SEMF01` | Prescription drugs (big-pharma line) | ~1947 |
| `CUUR0000SETB01` | Gasoline, all types (big-oil line) | 1976 |
| `CUUR0000SA0E` | Energy (aggregate) | 1957 |
| `CUUR0000SAH1` | Shelter / housing | 1953 |
| `CUUR0000SEMD` | Hospital & related services *(optional)* | **Dec 1996** |

**⭐ The common window is 1979.** The college-tuition subindex `CUUR0000SEEB01`
**begins December 1978** — the shortest series — so the clean common base for
indexing every sector to 100 is **1979 → latest** (~46 years). Every other sector
above reaches further back than 1978 and is simply truncated to the common start.
`CUUR0000SEMD` (hospital services) begins **1996**, so it must **not** anchor the
1979 window and is kept **out of the headline chart** (a late-window detail only).

**Caveats to carry forward** (written into `_sources.series_breaks` below and
SOURCES.md): tuition subindex starts Dec-1978 (the window floor); hospital
services starts 1996; **NSA only** — never mix in a `CUUS…`/`CUSR…` seasonally-
adjusted ID (the gasoline trap: use `CUUR0000SETB01`, not the `CUUS` twin); CPI
subindices embed BLS hedonic quality adjustment and periodic weight updates; the
tuition subindex tracks **published-price** movement, not net-of-aid price.

**Keyless BLS API windowing.** The public API returns **≤10 years per request**
(25 requests/day), so the 1979→2025 span is fetched in **five ≤10-year windows**,
with **all nine series IDs batched into each call** (≈5 calls total, not one call
per series per year). An optional `BLS_API_KEY` in the gitignored `.env` raises
the limits but is not required.

**Prior art (cited, not copied).** This chart is the longer-window extension of
the AEI / Mark J. Perry **"Chart of the Century"** — the well-known "price change
by sector since ~2000" line chart built from exactly these BLS CPI subindices. We
**cite it as the methodology reference / prior art** and differentiate by (a) a
longer window back to 1979, (b) the explicit "big pharma / big oil / big
education" framing, and (c) our own brand styling. We do **not** reproduce its
image or text. (humanprogress.org / AEI publish it annually.)
"""
)

code(
    r"""
import pandas as pd

cpi_cfg = cfg["sources"]["cpi_u"]
sector_series = list(cpi_cfg["series"].keys())           # all 9 CUUR sector IDs
sec_start = int(cpi_cfg.get("sectors_start_year", 1979))  # 1979 (tuition floor)
sec_end   = int(cpi_cfg.get("sectors_end_year", 2025))    # request through 2025
api_key = os.environ.get("BLS_API_KEY")                   # optional; gitignored .env

# Build <=10-year windows across 1979..2025. ALL nine series are batched into
# ONE call per window (not one call per series) to respect the 25 req/day limit:
# e.g. 1979-1988, 1989-1998, 1999-2008, 2009-2018, 2019-2025  ->  5 calls total.
windows = []
w0 = sec_start
while w0 <= sec_end:
    w1 = min(w0 + 9, sec_end)
    windows.append((w0, w1))
    w0 = w1 + 1
print(f"Fetching {len(sector_series)} CPI sector series over {len(windows)} windows "
      f"(<=10 yr each, all series batched per call): {windows}")

frames = []
for (sy, ey) in windows:
    frames.append(fetch_bls_series(sector_series, sy, ey, annual=True, api_key=api_key))
df_sectors = pd.concat(frames, ignore_index=True)

# Save the raw long-format payload verbatim to data/raw (this IS the raw artifact).
sectors_dest = raw_path(cfg, "cpi_u/cpi_sectors_raw.csv")
df_sectors.to_csv(sectors_dest, index=False)

# Load UNTOUCHED into DuckDB — raw stage, no transforms (cleaning is 02-clean).
load_to_duckdb(df_sectors, "cpi_sectors_raw", con)

print("Saved raw CSV :", sectors_dest)
print("cpi_sectors_raw: rows =", f"{df_sectors.shape[0]:,}", " cols =", df_sectors.shape[1])
yr_min, yr_max = con.execute(
    "SELECT MIN(TRY_CAST(year AS INT)), MAX(TRY_CAST(year AS INT)) FROM cpi_sectors_raw"
).fetchone()
print("Year range    :", yr_min, "->", yr_max)
print("Series present:", sorted(con.execute(
    "SELECT DISTINCT series_id FROM cpi_sectors_raw"
).df()["series_id"].tolist()))
"""
)

code(
    r"""
# Representative peek — annual-average (M13) index values for a few sectors at
# the window floor (1979) and a recent year, confirming the raw table loaded.
con.execute(
    "SELECT series_id, year, period, value FROM cpi_sectors_raw "
    "WHERE period='M13' AND series_id IN ('CUUR0000SA0','CUUR0000SEEB01','CUUR0000SAM2','CUUR0000SETB01') "
    "AND year IN ('1979','2024') ORDER BY series_id, year"
).df()
"""
)

code(
    r"""
# Per-series earliest annual-average (M13) year — confirms the common-window
# story: tuition (SEEB01) floors at ~1979, hospital services (SEMD) at ~1996.
con.execute(
    "SELECT series_id, MIN(TRY_CAST(year AS INT)) AS first_year, "
    "MAX(TRY_CAST(year AS INT)) AS last_year, COUNT(*) AS n_rows "
    "FROM cpi_sectors_raw WHERE period='M13' GROUP BY series_id ORDER BY first_year, series_id"
).df()
"""
)

code(
    r"""
register_source(
    con,
    table="cpi_sectors_raw",
    name="BLS CPI-U sector subindices (big-education relative-inflation set)",
    url=cpi_cfg["api_url"],
    license="Public domain (U.S. federal government work)",
    notes=("BLS CPI for All Urban Consumers, U.S. city average, NSA. Nine sector subindices for the "
           "reframed 'has higher-ed cost outpaced other sectors' headline: CUUR0000SA0 (All Items), "
           "CUUR0000SEEB01 (college tuition & fees), CUUR0000SAM (medical care all), CUUR0000SAM2 "
           "(medical care services), CUUR0000SEMF01 (prescription drugs), CUUR0000SETB01 (gasoline "
           "all types), CUUR0000SA0E (energy), CUUR0000SAH1 (shelter), CUUR0000SEMD (hospital & "
           "related services, optional/late-window). Long format: series_id, year, period "
           "(M01-M12 monthly, M13 annual avg), value. Fetched 1979-2025 via the keyless BLS public "
           "API in five <=10-year windows, all series batched per call. Prior art: AEI/Mark-Perry "
           "'Chart of the Century' — extended here with a longer 1979 window and our own framing "
           "(cited, not copied)."),
    retrieved=RETRIEVED,
    methodology=("BLS public timeseries API v2 (keyless), M13 annual averages, 1979-2025, U.S. city "
                 "average, NOT seasonally adjusted. Each sector re-indexed to 100 at a common base "
                 "year (1979) in 03-prepare; the published 1982-84=100 base is irrelevant once "
                 "re-indexed. Gasoline uses the CUUR (unadjusted) ID, never the CUUS SA twin."),
    series_breaks=("College-tuition subindex CUUR0000SEEB01 begins Dec 1978 -> sets the 1979 common "
                   "window; every other sector reaches further back and is truncated to it. "
                   "Hospital & related services CUUR0000SEMD begins Dec 1996 -> excluded from the "
                   "1979 common window / headline chart (late-window detail only). NSA only (never "
                   "mix with CUUS/CUSR seasonally-adjusted IDs). CPI subindices embed BLS hedonic "
                   "quality adjustment and periodic weight updates; the tuition subindex tracks "
                   "published (sticker-ish) price movement, not net-of-grant-aid price. Subindex "
                   "scope/title revisions over time (e.g. prescription drugs) apply per BLS docs."),
)
print("Registered cpi_sectors_raw.")
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Verify — raw tables + provenance

Confirm every `*_raw` table is populated and that `_sources` has one row per
table.
"""
)

code(
    r"""
tables = con.execute(
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_name LIKE '%_raw' ORDER BY table_name"
).df()["table_name"].tolist()

print("Raw tables and row counts")
print("-" * 46)
total = 0
for t in tables:
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    total += n
    print(f"  {t:<34} {n:>9,}")
print("-" * 46)
print(f"  {'TOTAL':<34} {total:>9,}   ({len(tables)} tables)")
"""
)

code(
    """
# One provenance row per raw table.
src = get_sources(con)
print("_sources rows:", len(src))
src[["duckdb_table", "source_name", "retrieved"]]
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
**Next:** `02-clean.ipynb` — load these raw tables, harmonize the GASB/FASB
finance categories separately, normalize per-FTE, and join tuition to
institutional characteristics.
"""
)

# ---------------------------------------------------------------------------
nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}

out = Path("notebooks/01-ingest.ipynb")
nbf.write(nb, str(out))
print("Wrote", out, "with", len(cells), "cells")
