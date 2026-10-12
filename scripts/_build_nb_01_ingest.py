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
    download_nces_digest_xlsx,
    read_nces_digest_tuition_longrun,
    download_delta_cost,
    read_delta_cost,
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

# IDEMPOTENT CACHE GUARD — the keyless BLS public API is capped at 25 requests/day,
# so re-executing this notebook must NOT re-pull if the raw artifact is already on
# disk. If data/raw/cpi_u/cpi_u_raw.csv exists (the verbatim BLS payload saved on
# the first run), reload it; only hit the API when the cache is absent.
cpi_dest = raw_path(cfg, "cpi_u/cpi_u_raw.csv")
if cpi_dest.exists():
    df_cpi = pd.read_csv(cpi_dest)
    print("Loaded cpi_u_raw from cache (no BLS API call):", cpi_dest)
else:
    # Keyless API allows <=10 years/request -> split 2000-2024 into two windows.
    frames = []
    for (sy, ey) in [(2000, 2009), (2010, 2024)]:
        frames.append(fetch_bls_series(series_ids, sy, ey, annual=True, api_key=api_key))
    df_cpi = pd.concat(frames, ignore_index=True)
    df_cpi.to_csv(cpi_dest, index=False)  # verbatim raw artifact

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
# IDEMPOTENT CACHE GUARD — same 25-req/day BLS cap as the pair above. If the
# verbatim sector payload is already on disk (data/raw/cpi_u/cpi_sectors_raw.csv),
# reload it instead of re-hitting the API on every re-execution.
sectors_dest = raw_path(cfg, "cpi_u/cpi_sectors_raw.csv")
if sectors_dest.exists():
    df_sectors = pd.read_csv(sectors_dest)
    print("Loaded cpi_sectors_raw from cache (no BLS API call):", sectors_dest)
else:
    print(f"Fetching {len(sector_series)} CPI sector series over {len(windows)} windows "
          f"(<=10 yr each, all series batched per call): {windows}")
    frames = []
    for (sy, ey) in windows:
        frames.append(fetch_bls_series(sector_series, sy, ey, annual=True, api_key=api_key))
    df_sectors = pd.concat(frames, ignore_index=True)
    df_sectors.to_csv(sectors_dest, index=False)  # verbatim raw artifact

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

# ===========================================================================
# REFRAME EXPANSION (second wave) — Sources A, B, C, D
# ===========================================================================
md(
    r"""
---
# ⭐ REFRAME EXPANSION — four more sources (A–D)

The CPI sector set above answers **Suspicion 1** (has higher-ed cost outpaced
other sectors' inflation). The four sources below deepen the project per
`SECTOR-COMPARISON-INVESTIGATION.md` §3 and `HISTORICAL-DEPTH-INVESTIGATION.md`:

| | Source | Raw table(s) | Story it feeds |
|---|---|---|---|
| **A** | NCES Digest **Table 330.10** (tuition 1963-64 → latest, current + constant-$) | `nces_tuition_longrun_raw` | The deep tuition skyrocket line |
| **B** | NCES **Delta Cost Project** DB 1987-2012 (harmonized spending-by-function + FTE) | `delta_cost_raw` | Admin-vs-classroom spending mix back to 1987 |
| **C** | **Raw IPEDS finance tail** 2013-2021 (`F####_F1A`/`F####_F2`/`EFIA####`) | `ipeds_finance_{gasb,fasb}_<yr>_raw`, `ipeds_fte_<yr>_raw` | Extend the spending mix to the present; clean the 2012 Delta seam |
| **D** | **IPEDS Human Resources** `S<year>_OC` 2013→2022 (SOC occupational categories) | `ipeds_hr_<yr>_raw` | Admin-vs-faculty-vs-enrollment headcount (the intuitive "bloat" proxy) |

Each is a U.S. federal / public-domain source (serious tier). Raw files land in
gitignored `data/raw/` verbatim; one `_sources` row per raw table carries the
methodology + series-break caveats. **The honest-framing rule carries through:**
the spending-mix story is **"non-instructional spending outgrew instruction," NOT
"administrators alone exploded"** — the authoritative literature (Kelchen, ACTA)
finds institutional-support grew ~like instruction while student services +
academic support grew faster. 02-clean and 03-prepare compute this honestly.
"""
)

# --------------------------------------------------------------------------- A
md(
    r"""
## Source A — NCES Digest **Table 330.10** · the long tuition skyrocket (1963-64 → latest)

**Publisher:** National Center for Education Statistics (NCES), Digest of
Education Statistics. **License:** public domain. **Auth:** none.

**Table 330.10** = *"Average undergraduate tuition and fees and room and board
rates charged for full-time students in degree-granting postsecondary
institutions, by level and control of institution."* It is the authoritative
national long-run series — selected academic years from **1963-64** to the latest,
in **both current and constant dollars**, split by **control** (all / public /
private) and **level** (all / 4-year / 2-year) and cost component (total /
tuition&fees / dorm / board).

**Edition confirmed at build time.** The Digest table HTML page embeds a wide
multi-level table `pandas.read_html` cannot parse cleanly, but every table page
offers a clean companion **Excel** at
`https://nces.ed.gov/programs/digest/<edition>/tables/xls/tabn330.10.asp → tabn330.10.xlsx`.
The build cell tries the newest edition first (`d24`, then `d23`, `d22`) and uses
the first whose Excel carries the "Current dollars" + "Constant <base> dollars"
tuition&fees columns from 1963-64. **The d24 edition's constant-$ base is
2023-24** (recorded in `_sources` + the clean step).

> **Series-break caveats (written into `_sources.series_breaks`):** these are
> NATIONAL AVERAGES, not per-institution; the institution universe and the
> room/board reporting basis shifted across Digest editions; the constant-dollar
> columns use **CPI-U All-Items** (a general deflator, not a tuition-specific one);
> the published price is **sticker**, not net-of-grant-aid; the Digest table NUMBER
> itself drifts by edition (345/349/320/330.10).

**Anchors to sanity-check (asserted in 02-clean, not here):** public 4-year
tuition&fees ≈ **\$243** current (1963-64) → ≈ **\$9,750** current (2022-23).
"""
)

code(
    r"""
# Pick the newest Digest edition whose 330.10 Excel carries the full 1963-64 series.
import requests as _rq

DIGEST_EDITIONS = ["d24", "d23", "d22"]
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
nces_tuition_url = None
nces_edition = None
for ed in DIGEST_EDITIONS:
    cand = f"https://nces.ed.gov/programs/digest/{ed}/tables/xls/tabn330.10.xlsx"
    try:
        r = _rq.head(cand, headers=_UA, timeout=30, allow_redirects=True)
        if r.status_code == 200:
            nces_tuition_url, nces_edition = cand, ed
            break
    except Exception as e:  # noqa: BLE001
        print(f"  {ed}: {e}")
assert nces_tuition_url, "No NCES Digest 330.10 Excel edition resolved (d24/d23/d22 all failed)."
print(f"Using NCES Digest edition {nces_edition}: {nces_tuition_url}")

# Download the Excel verbatim into data/raw/nces/ and load UNTOUCHED into DuckDB.
nces_xlsx = download_nces_digest_xlsx(nces_tuition_url, cfg, "dt_330_10.xlsx")
df_tuition_long = read_nces_digest_tuition_longrun(nces_xlsx)
load_to_duckdb(df_tuition_long, "nces_tuition_longrun_raw", con)

nces_base_year = int(df_tuition_long["base_year"].dropna().iloc[0])
print("Saved raw Excel :", nces_xlsx)
print("nces_tuition_longrun_raw rows =", f"{len(df_tuition_long):,}",
      " constant-$ base year =", nces_base_year)
print("controls:", sorted(df_tuition_long["control"].unique()),
      "| basis:", sorted(df_tuition_long["dollar_basis"].unique()),
      "| year range:", int(df_tuition_long["year_start"].min()), "->",
      int(df_tuition_long["year_start"].max()))

# Anchor peek (public 4-yr tuition&fees, current $): 1963-64 and 2022-23.
pub4 = df_tuition_long[(df_tuition_long.control == "public")
                       & (df_tuition_long.level == "4-year")
                       & (df_tuition_long.cost_component == "tuition_fees")
                       & (df_tuition_long.dollar_basis == "current")]
for ys in (1963, 2022):
    row = pub4[pub4.year_start == ys]
    if len(row):
        print(f"  public 4-yr t&f current {ys}: ${float(row.value.iloc[0]):,.0f}")
"""
)

code(
    r"""
register_source(
    con,
    table="nces_tuition_longrun_raw",
    name=f"NCES Digest of Education Statistics Table 330.10 ({nces_edition})",
    url=nces_tuition_url,
    license="Public domain (U.S. federal government work)",
    notes=("National average undergraduate tuition/fees/room/board by level (all/4-yr/2-yr) and "
           "control (all/public/private), selected academic years 1963-64 -> latest, in BOTH "
           "current and constant dollars. Parsed from the Digest table's companion Excel "
           f"(edition {nces_edition}; HTML read_html cannot parse the multi-level table). Tidy long: "
           "academic_year, year_start, control, level, dollar_basis, base_year, cost_component, value."),
    retrieved=RETRIEVED,
    methodology=(f"NCES Digest Table 330.10 ({nces_edition}). Constant-dollar columns are NCES's own "
                 f"CPI-U All-Items adjustment (base year = {nces_base_year}-{str(nces_base_year+1)[-2:]}). "
                 "National averages for full-time students at degree-granting institutions."),
    series_breaks=("NATIONAL AVERAGES, not per-institution. The institution universe and the "
                   "room/board reporting basis shifted across Digest editions (e.g. 'paid by FTE "
                   "students' vs 'charged for full-time students'; the private column folds for-profits "
                   "in some editions). Constant dollars use CPI-U All-Items (a general deflator, not a "
                   "tuition-specific one). Published (sticker) price, not net-of-grant-aid. The Digest "
                   "table NUMBER drifts by edition (345/349/320/330.10)."),
)
print("Registered nces_tuition_longrun_raw.")
"""
)

# --------------------------------------------------------------------------- B
md(
    r"""
## Source B — NCES **Delta Cost Project** Database 1987-2012 · admin-vs-classroom depth

**Publisher:** NCES (IPEDS Analytics: Delta Cost Project). **License:** public
domain. **Auth:** none.

The Delta Cost Project DB is the **NCES-harmonized longitudinal IPEDS**
finance+enrollment+staffing panel, academic years **1986-87 → 2011-12**, with
expense-by-function and FTE **harmonized across the Common-Form / FASB / GASB /
Aligned-Form reporting-standard changes** and carrying its own **constructed
12-month FTE**. It is the ONLY clean way to take the admin-vs-classroom spending
mix back to 1987 (raw IPEDS finance stems/codes are not stable across those
breaks; Delta already reconciled them).

**Download (confirmed live at build):** one ~115 MB zip at
`https://nces.ed.gov/ipeds/deltacostproject/download/IPEDS_Analytics_DCP_87_12_CSV.zip`,
holding two CSVs — `delta_public_87_99.csv` and `delta_public_00_12.csv` ("public"
= public RELEASE, not public institutions). `download_delta_cost()` saves the zip
verbatim into gitignored `data/raw/delta/`; `read_delta_cost()` reads **only the
needed columns** (the file is 974 vars wide) and concatenates both spans into one
1987-2012 frame. The function totals are the CFI-method `<fn>01` columns
(`instruction01`, `research01`, `pubserv01`, `acadsupp01`, `studserv01`,
`instsupp01` = institutional support = admin), FTE = `fte12mn`, `control` =
1 public / 2 private-nonprofit / 3 for-profit.

> **Series-break / known-controversy caveats (into `_sources.series_breaks`):**
> Delta is a **DERIVED / imputed** product — cite **Jaquette & Parra, "The Problem
> with the Delta Cost Project Database."** It harmonizes the FASB-1997 /
> GASB-2002-04 / Aligned-Form-2008-10 breaks but **ENDS at 2011-12** (a seam to the
> raw-IPEDS 2013+ tail added in Source C). Prefer spending **SHARES** over absolute
> per-FTE where imputation risk is higher. The raw table is loaded UNTOUCHED; the
> share/per-FTE computation + for-profit filtering happen in 02-clean.
"""
)

code(
    r"""
# One large (~115 MB) zip; download_delta_cost() is idempotent (skips if present).
DELTA_URL = "https://nces.ed.gov/ipeds/deltacostproject/download/IPEDS_Analytics_DCP_87_12_CSV.zip"
delta_zip = download_delta_cost(cfg, DELTA_URL)
print("Delta zip:", delta_zip, f"({delta_zip.stat().st_size:,} bytes)")

df_delta = read_delta_cost(delta_zip)          # needed-columns subset, both spans
load_to_duckdb(df_delta, "delta_cost_raw", con)  # UNTOUCHED (NCES already harmonized)
print("delta_cost_raw rows =", f"{len(df_delta):,}", " cols =", df_delta.shape[1])
print("year range:", int(df_delta.academicyear.min()), "->", int(df_delta.academicyear.max()))
print("control counts:", df_delta.control.value_counts(dropna=False).to_dict())
print("columns:", df_delta.columns.tolist())
"""
)

code(
    r"""
register_source(
    con,
    table="delta_cost_raw",
    name="NCES IPEDS Analytics: Delta Cost Project Database 1987-2012",
    url="https://nces.ed.gov/ipeds/use-the-data/delta-cost-project-finance-data",
    license="Public domain (U.S. federal government work)",
    notes=("NCES-harmonized longitudinal IPEDS finance+enrollment+staffing, academic years 1986-87 -> "
           "2011-12. Needed-column subset loaded (file is 974 vars): unitid, academicyear, control, "
           "sector, fte12mn (constructed 12-mo FTE), fte_count, the CFI-method function totals "
           "instruction01/research01/pubserv01/acadsupp01/studserv01/instsupp01 (instsupp01 = "
           "institutional support = admin), and cpi_scalar_2012 (Delta's own CPI-to-2012 scalar). "
           "control: 1=public, 2=private-nonprofit, 3=for-profit."),
    retrieved=RETRIEVED,
    methodology=("Expense-by-function and FTE harmonized by NCES across the Common-Form/FASB/GASB/"
                 "Aligned-Form reporting-standard changes; carries its own constructed 12-month FTE "
                 "(fte12mn). Loaded verbatim; for-profit filtering + per-FTE/SHARE computation happen "
                 "in 02-clean."),
    series_breaks=("Delta is a DERIVED/imputed product (cite Jaquette & Parra, 'The Problem with the "
                   "Delta Cost Project Database'). It harmonizes the FASB-1997 / GASB-2002-04 / "
                   "Aligned-Form-2008-10 reporting-standard breaks but ENDS at 2011-12 -> seam to the "
                   "raw-IPEDS 2013+ finance tail (Source C) at 2012. Prefer spending SHARES over "
                   "absolute per-FTE where imputation risk is higher."),
)
print("Registered delta_cost_raw.")
"""
)

# --------------------------------------------------------------------------- C
md(
    r"""
## Source C — Raw IPEDS **finance tail** 2013-2021 · extend the spending mix to the present

To carry the admin-vs-classroom spending mix from Delta's 2011-12 endpoint up to
the present, pull the raw IPEDS **Finance** survey for the intermediate years
between the project's existing 2012 and 2022, reusing the same
`download_ipeds_survey()` / `read_ipeds_zip()` helpers and the stable ZIP pattern
`https://nces.ed.gov/ipeds/datacenter/data/<FILE>.zip`.

**Years:** **2016, 2019** (two clean mid-points — enough to establish the
2012→2022 trend without 9 near-identical pulls). **Files per year:** `F<yy><yy>_F1A`
(GASB/public), `F<yy><yy>_F2` (FASB/private nonprofit), `EFIA<year>` (12-month FTE).
Fiscal-year stem convention: FY2016 = `F1516`, FY2019 = `F1819`.

**⭐ Function-code confirmation (done at build, per HARMONIZATION-DESIGN §1.2).**
These years are all **post-Aligned-Form (2008-10)**, so the modern GASB **F1C**
(F1C011 instruction … F1C071 institutional support) and FASB **F2E** (F2E011 …
F2E061) function-total codes the project already uses hold — but the build cell
**asserts each code is present in each year's table before trusting it** (same
`FUNCTION_CROSSWALK` used by `02-clean`). If a year's stem/codes can't be confirmed,
that year is dropped (the others kept) and the drop is noted. Raw tables are
loaded UNTOUCHED; the GASB/FASB harmonization onto Delta's categories happens in
02-clean.

> **Series-break caveat (into `_sources`):** a **seam at 2011-12** where the Delta
> harmonized series ends and this raw-IPEDS tail begins. GASB isolates O&M-of-plant
> while FASB distributes it (O&M excluded from the admin/classroom numerators per
> HARMONIZATION-DESIGN §1.2); function-total codes verified present per year.
"""
)

code(
    r"""
from src.clean_quality import FUNCTION_CROSSWALK  # dictionary-confirmed F1C/F2E codes

# Source-C finance tail years -> (fiscal stem prefix). FY2016=F1516, FY2019=F1819.
FINANCE_TAIL = {2016: "F1516", 2019: "F1819"}
GASB_CODES = [g for g, _ in FUNCTION_CROSSWALK.values()]
FASB_CODES = [f for _, f in FUNCTION_CROSSWALK.values()]

tail_loaded = {}
tail_dropped = []
for yr, stem in FINANCE_TAIL.items():
    try:
        # GASB (public) + FASB (private nonprofit) + 12-month FTE (EFIA).
        gasb_zip = download_ipeds_survey(f"{stem}_F1A", cfg)
        fasb_zip = download_ipeds_survey(f"{stem}_F2", cfg)
        efia_zip = download_ipeds_survey(f"EFIA{yr}", cfg)
        g = read_ipeds_zip(gasb_zip); f = read_ipeds_zip(fasb_zip); e = read_ipeds_zip(efia_zip)
        g_have = {c.upper() for c in g.columns}; f_have = {c.upper() for c in f.columns}
        g_miss = [c for c in GASB_CODES if c not in g_have]
        f_miss = [c for c in FASB_CODES if c not in f_have]
        if g_miss or f_miss:
            tail_dropped.append((yr, f"missing GASB {g_miss} / FASB {f_miss}"))
            print(f"  ⚠ {yr}: DROPPED — missing function codes GASB={g_miss} FASB={f_miss}")
            continue
        load_to_duckdb(g, f"ipeds_finance_gasb_{yr}_raw", con)
        load_to_duckdb(f, f"ipeds_finance_fasb_{yr}_raw", con)
        load_to_duckdb(e, f"ipeds_fte_{yr}_raw", con)
        tail_loaded[yr] = (g.shape, f.shape, e.shape)
        print(f"  {yr} ({stem}): GASB {g.shape[0]:,} / FASB {f.shape[0]:,} / EFIA {e.shape[0]:,}  "
              f"— all function codes present")
    except Exception as exc:  # noqa: BLE001
        tail_dropped.append((yr, str(exc)))
        print(f"  ⚠ {yr}: DROPPED — {exc}")

print("\nfinance-tail years loaded:", sorted(tail_loaded), "| dropped:", tail_dropped)
assert tail_loaded, "No finance-tail year could be ingested — Source C failed entirely."
"""
)

code(
    r"""
IPEDS_URL_TMPL_C = "https://nces.ed.gov/ipeds/datacenter/data/{file}.zip"
for yr, stem in FINANCE_TAIL.items():
    if yr not in tail_loaded:
        continue
    for std, suffix, tbl in [("GASB", "F1A", f"ipeds_finance_gasb_{yr}_raw"),
                             ("FASB", "F2",  f"ipeds_finance_fasb_{yr}_raw")]:
        register_source(
            con, table=tbl,
            name=f"IPEDS Finance {std} {stem}_{suffix} (NCES)",
            url=IPEDS_URL_TMPL_C.format(file=f"{stem}_{suffix}"),
            license="Public domain (U.S. federal government work)",
            notes=(f"Raw IPEDS Finance (Aligned Form) {std} FY{yr-1}-{str(yr)[-2:]} — expenses by "
                   f"function (F1C*/F2E*), harmonized onto Delta's category definitions in 02-clean. "
                   f"Fills the 2012->2022 spending-mix tail between the project's existing endpoints."),
            retrieved=RETRIEVED,
            methodology=(f"Raw IPEDS Finance {std} complete data file, FY{yr}; expenses by function + "
                         "EFIA 12-month FTE; harmonized onto Delta categories (02-clean)."),
            series_breaks=("Seam at 2011-12 where the Delta harmonized series ends and the raw-IPEDS "
                           "tail begins. GASB isolates O&M-of-plant while FASB distributes it (O&M "
                           "excluded from admin/classroom numerators per HARMONIZATION-DESIGN §1.2). "
                           "Function-total codes verified present for this year before parsing."),
        )
    register_source(
        con, table=f"ipeds_fte_{yr}_raw",
        name=f"IPEDS EFIA{yr} 12-month FTE (NCES)",
        url=IPEDS_URL_TMPL_C.format(file=f"EFIA{yr}"),
        license="Public domain (U.S. federal government work)",
        notes=f"IPEDS 12-month instructional-activity FTE (EFIA), FY{yr} — the per-FTE denominator.",
        retrieved=RETRIEVED,
        methodology="IPEDS EFIA 12-month FTE (FTEUG + FTEGD); authoritative IPEDS FTE for the finance tail.",
        series_breaks="IPEDS enrollment/FTE definitions have minor cross-year revisions; FTE basis stable 2013+.",
    )
print("Registered finance-tail sources for years:", sorted(tail_loaded))
"""
)

# --------------------------------------------------------------------------- D
md(
    r"""
## Source D — IPEDS **Human Resources** `S<year>_OC` · admin-vs-faculty headcount (the intuitive proxy)

**Publisher:** NCES / IPEDS Human Resources component. **License:** public domain.

The HR **staff-by-occupational-category** file (`S<year>_OC`, same ZIP pattern) is
the most intuitive "bloat" proxy: how many **administrators (Management)** vs
**faculty (Instructional staff)** an institution employs, against enrollment.

**Clean window = 2012-13 → present ONLY.** ⭐ **HARD series break at 2012-13:**
IPEDS replaced the old primary-function / EEO occupational-activity categories
with **2010-SOC-based** categories effective the 2012-13 collection, so this series
is comparable only from 2012-13 forward. **No pre-2012 crosswalk is attempted.**

**Years pulled:** **2013, 2016, 2019, 2022** (endpoints + two mid-points for a
trend). **Occupational categories (confirmed from the S2022_OC data dictionary):**
the file is long, keyed by `STAFFCAT` (occupation × full/part-time) with `FTPT`
(1=all staff) and `HRTOTLT` (grand-total headcount). Admin = **STAFFCAT 1300
(Management)**; faculty = **STAFFCAT 1210 (Instructional staff)**; both taken at
`FTPT=1` (all staff). The denominator is the 12-month FTE (`EFIA<year>`) reused
from Source C (any missing EFIA years are pulled here).

> **Series-break caveat (into `_sources`):** the 2012-13 SOC-category replacement
> is a HARD break; this series is clean only from 2012-13 forward and is NOT
> comparable to earlier IPEDS staff categories. Raw tables loaded UNTOUCHED;
> the admin/faculty aggregation happens in 02-clean.
"""
)

code(
    r"""
HR_YEARS = [2013, 2016, 2019, 2022]
hr_loaded = {}
hr_dropped = []
for yr in HR_YEARS:
    try:
        hr_zip = download_ipeds_survey(f"S{yr}_OC", cfg)
        hr = read_ipeds_zip(hr_zip)
        have = {c.upper() for c in hr.columns}
        need = {"UNITID", "STAFFCAT", "FTPT", "HRTOTLT"}
        miss = [c for c in need if c not in have]
        if miss:
            hr_dropped.append((yr, f"missing columns {miss}"))
            print(f"  ⚠ {yr}: DROPPED — missing {miss}")
            continue
        load_to_duckdb(hr, f"ipeds_hr_{yr}_raw", con)
        hr_loaded[yr] = hr.shape
        # Pull EFIA for any HR year not already present from Source C.
        if f"ipeds_fte_{yr}_raw" not in {t[0] for t in con.execute('SHOW TABLES').fetchall()}:
            efia = read_ipeds_zip(download_ipeds_survey(f"EFIA{yr}", cfg))
            load_to_duckdb(efia, f"ipeds_fte_{yr}_raw", con)
            print(f"  {yr}: pulled EFIA{yr} ({efia.shape[0]:,} rows)")
        print(f"  {yr} (S{yr}_OC): {hr.shape[0]:,} rows — STAFFCAT/FTPT/HRTOTLT present")
    except Exception as exc:  # noqa: BLE001
        hr_dropped.append((yr, str(exc)))
        print(f"  ⚠ {yr}: DROPPED — {exc}")

print("\nHR years loaded:", sorted(hr_loaded), "| dropped:", hr_dropped)
assert hr_loaded, "No IPEDS HR year could be ingested — Source D failed entirely."
"""
)

code(
    r"""
for yr in HR_YEARS:
    if yr not in hr_loaded:
        continue
    register_source(
        con, table=f"ipeds_hr_{yr}_raw",
        name=f"IPEDS Human Resources S{yr}_OC (NCES)",
        url=f"https://nces.ed.gov/ipeds/datacenter/data/S{yr}_OC.zip",
        license="Public domain (U.S. federal government work)",
        notes=(f"IPEDS HR staff by occupational category (SOC-based), {yr}. Long, keyed by STAFFCAT "
               "(occupation x full/part-time) with FTPT (1=all staff) and HRTOTLT (grand-total "
               "headcount). 'Administrators/non-instructional' = STAFFCAT 1300 (Management); "
               "'faculty/instructional' = STAFFCAT 1210 (Instructional staff), both at FTPT=1. "
               "Denominator = EFIA 12-month FTE."),
        retrieved=RETRIEVED,
        methodology=("IPEDS Human Resources occupational-category staff counts; admin = Management, "
                     "faculty = instructional staff; aggregation + FTE join in 02-clean."),
        series_breaks=("⭐ HARD break at 2012-13: IPEDS replaced the old primary-function/EEO "
                       "occupational-activity categories with 2010-SOC-based categories, so this series "
                       "is clean only from 2012-13 forward; NO pre-2012 crosswalk attempted."),
    )
print("Registered HR sources for years:", sorted(hr_loaded))
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
