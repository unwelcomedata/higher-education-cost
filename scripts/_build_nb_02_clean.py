"""Build notebooks/02-clean.ipynb for higher-education-cost via nbformat.

Run from the project root with the project venv:
    .venv/bin/python scripts/_build_nb_02_clean.py

Produces the canonical-record cleaning notebook: a markdown cell per step
(narrating WHAT + WHY at its pipeline stage) followed by a code cell that calls
the src/clean_quality.py helper. ALL cleaning happens inside DuckDB. The
notebook is executed headless with:
    .venv/bin/python -m nbconvert --to notebook --execute --inplace notebooks/02-clean.ipynb

Structure/style copied from scripts/_build_nb_01_ingest.py.
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
# 02 — Clean · higher-education-cost

**Goal of this stage:** turn the 12 raw IPEDS/Scorecard/CPI tables (plus two
re-ingested sources) into **harmonized, quality-checked interim `_clean`
tables**, saved as Parquet to `data/interim/` and created as `_clean` DuckDB
tables. **ALL cleaning happens inside DuckDB** (via `run_sql` / `clean_table`),
never with pandas chained transforms — per workspace norms.

The one load-bearing methodology decision — reconciling IPEDS Finance **GASB
(public)** vs **FASB (private nonprofit)** expenses-by-function into a comparable
*admin-vs-classroom* schema — is settled in
`artifacts/HARMONIZATION-DESIGN.md`. This notebook implements it.

**What gets built (design §8.1):**

| Interim `_clean` table | Grain | What it is |
|---|---|---|
| `hd_clean` | UNITID × year | Institution directory (state, sector, control, level) |
| `finance_functions_clean` | UNITID × year × function | **The harmonized spine** — GASB+FASB melted onto one 6-function schema, each row tagged `control` |
| `finance_totals_clean` | UNITID × year × control | Sidecar per-standard grand totals (reconciliation only) |
| `fte_clean` | UNITID × year | 12-month FTE from the re-ingested EFIA file |
| `charges_clean` | UNITID × year | Sticker tuition & fees, three residency tiers |
| `net_price_clean` | UNITID (snapshot) | Scorecard net price — kept DISTINCT from sticker |
| `cpi_clean` | year | CPI-U All-Items + tuition subindex, annual averages |

**⭐ Series-break caveats carried forward** (into `_sources` + `SOURCES.md`):
GASB isolates operation-and-maintenance of plant as its own function while FASB
distributes it into the other functions, so the harmonized functions are
comparable only to within that allocation difference; raw totals are
standard-specific and never compared across standards; IPEDS survey definitions
shifted 2011-12 → 2021-22 (treated as two series, not a continuous panel);
institutions enter/exit between the two years.
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

from src.ingest import (
    load_config,
    download_ipeds_survey,
    read_ipeds_zip,
    fetch_bls_series,
    download_file,
    raw_path,
)
from src import clean_quality as cq

cfg = load_config("config.yaml")
con = cq.get_connection(cfg)   # opens data/project.duckdb (single-writer!)
RETRIEVED = "2026-09-30"
print("Project:", cfg["project_name"])
print("DuckDB :", cfg["settings"]["duckdb_file"])
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Blocker B1 (re-ingest) — IPEDS 12-month FTE (`EFIA`)

The already-loaded EFFY enrollment file carries **headcount with no FTE and no
full-time/part-time split** (design §4), so there is **no viable FTE
approximation** from it. The per-FTE metric needs IPEDS's own authoritative
**12-month FTE**, which lives in the derived **`EFIA`** survey file — not
previously ingested.

A new/expanded source is **ingestion**, so per the workspace stage-gate this
re-enters at `01-ingest`. It is placed here (a clearly-labeled re-ingest
section) rather than mutating the committed, APPROVED `01-ingest` notebook; it
uses the same `src/ingest.py` helpers and registers `_sources`.

**Source:** IPEDS `EFIA2022` / `EFIA2012` (NCES), public domain, no auth.
`https://nces.ed.gov/ipeds/datacenter/data/EFIA<year>.zip`. The authoritative
columns are **`FTEUG`** (reported 12-month undergraduate FTE) and **`FTEGD`**
(reported 12-month graduate FTE); one row per institution. We compute
`fte_total = FTEUG + FTEGD` in `fte_clean` below.
"""
)

code(
    r"""
EFIA_TABLES = {"EFIA2012": "ipeds_fte_2012_raw", "EFIA2022": "ipeds_fte_2022_raw"}

for survey_file, table in EFIA_TABLES.items():
    zip_path = download_ipeds_survey(survey_file, cfg)   # verbatim -> data/raw/ipeds/
    df = read_ipeds_zip(zip_path)
    df.columns = [c.strip() for c in df.columns]         # IPEDS pads a trailing col name
    cq.load_to_duckdb(df, table, con)
    fte_cols = [c for c in df.columns if "FTE" in c.upper()]
    print(f"{survey_file:>9}  ->  {table:<22}  rows={df.shape[0]:>6,}  FTE cols={fte_cols[:4]}")

    cq.register_source(
        con, table=table, name=f"IPEDS {survey_file} (NCES)",
        url=f"https://nces.ed.gov/ipeds/datacenter/data/{survey_file}.zip",
        license="Public domain (U.S. federal government work)",
        notes=("IPEDS 12-month instructional activity / FTE enrollment. FTEUG = reported "
               "undergraduate FTE, FTEGD = reported graduate FTE; one row per UNITID. "
               "Re-ingested in 02-clean because EFFY carries only headcount (no FTE)."),
        retrieved=RETRIEVED,
        methodology="IPEDS derived 12-month FTE (credit/clock-hour based); authoritative FTE for per-FTE normalization.",
        series_breaks="IPEDS survey definitions shifted 2011-12 vs 2021-22; treat the two years as separate series.",
    )

# Verify: FTE tables exist, non-empty, with the FTE column present.
for table in EFIA_TABLES.values():
    cols = {c.upper() for c in con.execute(f"SELECT * FROM {table} LIMIT 0").df().columns}
    n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    assert n > 0 and "FTEUG" in cols, f"{table} missing/empty or no FTEUG column"
print("B1 OK — EFIA FTE tables ingested with FTEUG present.")
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Blocker B2 (re-ingest) — BLS CPI-U through ≥2022

`cpi_u_raw` as first ingested stopped at **2019** (the keyless BLS API returns
≤10 years/request and the earlier two-window pull truncated). Without a **CY2022
annual-average (`M13`) All-Items** value, the 2021-22 dollars **cannot be
deflated** (design §5). We need `CUUR0000SA0` (All Items) and `CUUR0000SEEB01`
(college-tuition subindex) through 2022 — just the **two deflator / tuition-
comparison series**, not the full sector set.

**⭐ Quota-robust re-ingest (no wasted API calls).** The reframe's `01-ingest`
already pulled `cpi_sectors_raw` — which **contains these same two series
(`CUUR0000SA0`, `CUUR0000SEEB01`) across 1979–2025**, M13 annual averages, from
the SAME keyless BLS API. Because the public API is capped at **25 requests/day**
and the reframe ingest already spends several, this cell **prefers to rebuild
`cpi_u_raw` from `cpi_sectors_raw`** (zero network calls, identical BLS values).
It only falls back to a live `fetch_bls_series` pull if, for any reason,
`cpi_sectors_raw` is absent or missing a 2022 anchor. Either path lands the same
`cpi_u_raw` long-format table (series_id, year, period, value, …) with the
required M13 anchors.

Same stage-gate note as B1: this is ingestion, done here as a labeled re-ingest
section using the existing `src/ingest.py::fetch_bls_series`, and `_sources` is
re-registered. `BLS_API_KEY` (gitignored `.env`) is optional.
"""
)

code(
    r"""
cpi_cfg = cfg["sources"]["cpi_u"]
# cpi_u is the deflator + tuition-comparison layer: ONLY these two series.
DEFLATOR_SERIES = ["CUUR0000SA0", "CUUR0000SEEB01"]
api_key = os.environ.get("BLS_API_KEY")   # optional

def _cpi_from_sectors():
    '''Rebuild the two deflator series from the already-ingested cpi_sectors_raw
    (same BLS API, same values, 1979-2025) — no network call.'''
    have = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    if "cpi_sectors_raw" not in have:
        return None
    df = con.execute(
        "SELECT series_id, year, period, period_name, value, footnotes "
        "FROM cpi_sectors_raw WHERE series_id IN ('CUUR0000SA0','CUUR0000SEEB01')"
    ).df()
    if df.empty:
        return None
    # Must carry the 2022 All-Items M13 anchor, else it is not usable as a deflator.
    anchor = df[(df.series_id == "CUUR0000SA0") & (df.period == "M13") & (df.year.astype(str) == "2022")]
    return df if len(anchor) else None

df_cpi = _cpi_from_sectors()
source_path = "rebuilt from cpi_sectors_raw (no API call)"
if df_cpi is None:
    # Fallback: live pull of ONLY the two deflator series, windowed <=10 yr.
    print("cpi_sectors_raw unavailable/incomplete — falling back to a live BLS pull.")
    frames = []
    for (sy, ey) in [(2000, 2009), (2010, 2019), (2020, 2024)]:
        frames.append(fetch_bls_series(DEFLATOR_SERIES, sy, ey, annual=True, api_key=api_key))
    df_cpi = pd.concat(frames, ignore_index=True)
    source_path = "live BLS fetch_bls_series (3 windows)"

# Overwrite the raw artifact on disk + the raw table (this IS the BLS raw artifact).
cpi_dest = raw_path(cfg, "cpi_u/cpi_u_raw.csv")
df_cpi.to_csv(cpi_dest, index=False)
cq.load_to_duckdb(df_cpi, "cpi_u_raw", con)

yr_min, yr_max = con.execute("SELECT MIN(TRY_CAST(year AS INT)), MAX(TRY_CAST(year AS INT)) FROM cpi_u_raw").fetchone()
m13_count = con.execute(
    "SELECT COUNT(*) FROM cpi_u_raw WHERE series_id='CUUR0000SA0' AND period='M13' "
    "AND year IN ('2012','2022')"
).fetchone()[0]
print(f"cpi_u_raw ({source_path}): rows={len(df_cpi):,}  year range {yr_min}-{yr_max}  "
      f"All-Items M13 rows for 2012 & 2022 = {m13_count}")
assert m13_count == 2, "cpi_u_raw is missing an M13 All-Items annual average for 2012 and/or 2022"

cq.register_source(
    con, table="cpi_u_raw", name="BLS CPI-U (All Items + college tuition subindex)",
    url=cpi_cfg["api_url"], license="Public domain (U.S. federal government work)",
    notes=("BLS CPI for All Urban Consumers. CUUR0000SA0 (All Items, NSA) = real-dollar deflator; "
           "CUUR0000SEEB01 (college tuition & fees subindex) = tuition-vs-general-inflation comparison "
           "ONLY (never used to deflate spending). Long format with M13 annual averages. Rebuilt from "
           "cpi_sectors_raw (same BLS API/values) when available to respect the 25-req/day keyless cap."),
    retrieved=RETRIEVED,
    methodology=("BLS public timeseries API v2 (keyless). Rebuilt from the already-ingested "
                 "cpi_sectors_raw (both series present 1979-2025) to avoid extra API calls; falls "
                 "back to a live 3-window pull if that table is unavailable."),
    series_breaks="CPI-U base 1982-84=100, NSA. Used only as a ratio, so the base is irrelevant to deflation.",
)
print("B2 OK — cpi_u_raw ready through", yr_max)
"""
)

# ---------------------------------------------------------------------------
md(
    r"""
## Step 1b (REFRAME) — `cpi_sectors_clean` (CPI sector subindices → interim)

Clean the raw CPI **sector subindices** (`cpi_sectors_raw`, ingested in
`01-ingest` for the "big education vs other sectors" reframe) into the interim
table **`cpi_sectors_clean`**. This is a light, DuckDB-only pass — the raw table
is already tidy long-format from the BLS API; cleaning just:

1. **keeps the annual-average rows only** (`period = 'M13'`) — one value per
   sector per year, dropping the monthly rows;
2. **casts** `year` → INTEGER and `value` → DOUBLE (the API returns both as text);
3. **keeps** `series_id, year, value`;
4. **adds a human `sector` label column** from the config `series` map, so
   downstream charts never have to carry raw CUUR codes.

Saved as interim Parquet (`cpi_sectors_clean.parquet`) via the same
`save_interim` pattern used by every other `_clean` table. The re-indexing to a
common 1979 base (the chart-ready transform) is **`03-prepare`'s** job, not here
— `02` only standardizes.

**Caveats carried forward** (into `_sources`): NSA only; the college-tuition
subindex (`CUUR0000SEEB01`) begins Dec-1978 → the common-window floor is 1979;
hospital services (`CUUR0000SEMD`) begins 1996 → excluded from the 1979 headline
window; CPI embeds hedonic/weighting adjustment; the tuition subindex is a
published-price (not net-of-aid) measure.
"""
)

code(
    r"""
# Human sector labels from config (keep the short, chart-friendly phrasing).
SECTOR_LABELS = {
    "CUUR0000SA0":    "All items",
    "CUUR0000SEEB01": "College tuition & fees",
    "CUUR0000SAM":    "Medical care (all)",
    "CUUR0000SAM2":   "Medical care services",
    "CUUR0000SEMF01": "Prescription drugs",
    "CUUR0000SETB01": "Gasoline",
    "CUUR0000SA0E":   "Energy",
    "CUUR0000SAH1":   "Shelter",
    "CUUR0000SEMD":   "Hospital services",
}

# Register the label map as a tiny DuckDB relation so the whole clean is SQL.
labels_df = pd.DataFrame(
    [{"series_id": k, "sector": v} for k, v in SECTOR_LABELS.items()]
)
cq.load_to_duckdb(labels_df, "_cpi_sector_labels", con)

cpi_sectors = cq.run_sql(
    '''
    SELECT r.series_id,
           TRY_CAST(r.year AS INTEGER) AS year,
           TRY_CAST(r.value AS DOUBLE) AS value,
           l.sector
    FROM cpi_sectors_raw r
    LEFT JOIN _cpi_sector_labels l USING (series_id)
    WHERE r.period = 'M13'                 -- annual averages only
      AND TRY_CAST(r.value AS DOUBLE) IS NOT NULL
    ORDER BY r.series_id, year
    ''',
    con,
)
con.execute("DROP TABLE IF EXISTS _cpi_sector_labels")  # scratch, not an artifact

cq.quality_report(cpi_sectors, "cpi_sectors_clean", con,
                  required_columns=["series_id", "year", "value", "sector"])
cq.load_to_duckdb(cpi_sectors, "cpi_sectors_clean", con)
cq.save_interim(cpi_sectors, cfg, "cpi_sectors_clean.parquet")

# Every series must carry a non-null human label (no unmapped CUUR codes left).
unmapped = cpi_sectors[cpi_sectors["sector"].isna()]["series_id"].unique().tolist()
assert not unmapped, f"CPI series missing a sector label: {unmapped}"
print("Sectors cleaned:", sorted(cpi_sectors["sector"].unique()))
print("Year span      :", int(cpi_sectors["year"].min()), "->", int(cpi_sectors["year"].max()))
print("Rows per sector:\n", cpi_sectors.groupby("sector").size().to_string())
"""
)

code(
    r"""
cq.register_source(
    con, table="cpi_sectors_clean",
    name="BLS CPI-U sector subindices (cleaned, annual averages)",
    url=cfg["sources"]["cpi_u"]["api_url"],
    license="Public domain (U.S. federal government work)",
    notes=("Annual-average (M13) CPI-U NSA sector subindices for the big-education relative-inflation "
           "headline: All items, college tuition & fees, medical care (all), medical care services, "
           "prescription drugs, gasoline, energy, shelter, hospital services. One row per series_id x "
           "year with a human 'sector' label; re-indexed to a 1979 common base in 03-prepare."),
    retrieved=RETRIEVED,
    methodology="Light DuckDB clean of cpi_sectors_raw: keep M13 annual averages, cast year/value, add sector label.",
    series_breaks=("NSA only. College-tuition subindex (CUUR0000SEEB01) begins Dec-1978 -> 1979 common-window "
                   "floor; hospital services (CUUR0000SEMD) begins 1996 -> excluded from the 1979 headline. "
                   "CPI embeds hedonic/weighting adjustment; tuition subindex is published-price, not net-of-aid."),
)
print("Registered cpi_sectors_clean.")
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Step 2 — ⭐ Hard precondition: dictionary-confirm every finance function code

Column *values* were read from the DB during design, but column *meanings* were
not — and a naive "standard order" assumption is unsafe. Before building the
finance spine we confirm each used code's official `varTitle` against the
**IPEDS F1A / F2 data dictionaries** (the `varlist` sheet shipped as an `.xlsx`
inside each survey's `<FILE>_Dict.zip`), for **both** collection years.

> **⭐ The dictionary CORRECTED the design draft.** The draft crosswalk mapped
> GASB expenses-by-function to columns `F1E01…F1E07`. The F1A dictionary shows
> those are the **scholarships / grants** block (Pell grants, state grants, …),
> **not** expenses by function. The real GASB expenses-by-function block is
> **`F1C`**, and its function index differs from FASB's. The design's §1.2 rule
> is explicit — *"if any `varTitle` disagrees with the table, the dictionary
> wins and the crosswalk is corrected before building"* — so the implemented
> crosswalk (in `src/clean_quality.py::FUNCTION_CROSSWALK`) uses the
> dictionary-confirmed columns:
>
> | function | GASB (F1C) | FASB (F2E) |
> |---|---|---|
> | instruction | `F1C011` | `F2E011` |
> | research | `F1C021` | `F2E021` |
> | public_service | `F1C031` | `F2E031` |
> | academic_support | `F1C051` | `F2E041` |
> | student_services | `F1C061` | `F2E051` |
> | institutional_support (**= admin**) | `F1C071` | `F2E061` |
> | total_expenses (sidecar) | `F1C191` | `F2E131` |
>
> **Consequence:** the design flagged GASB `academic_support` as "sparse"
> (236/2,004) and excluded it from cross-sector charts — but that was the WRONG
> column (`F1E04` = local-government grants). The correct `F1C051` is
> well-populated in both sectors (coverage printed by `quality_report` below), so
> that sparsity rationale is defunct. `02-clean` carries `academic_support` in
> the spine and reports its true coverage; whether to use it in public-vs-private
> charts is a `03-prepare` decision, flagged there.
"""
)

code(
    r"""
# Download the four finance data-dictionary ZIPs (varlist sheet) and confirm titles.
DICT_FILES = {
    "gasb_2012": "F1112_F1A", "gasb_2022": "F2122_F1A",
    "fasb_2012": "F1112_F2",  "fasb_2022": "F2122_F2",
}
dict_zip_paths = {}
for label, stem in DICT_FILES.items():
    dest = raw_path(cfg, f"ipeds/{stem}_Dict.zip")
    if not dest.exists():
        download_file(f"https://nces.ed.gov/ipeds/datacenter/data/{stem}_Dict.zip", dest)
    dict_zip_paths[label] = dest

confirmed = cq.confirm_finance_dictionary(con, dict_zip_paths)
print("Confirmed varTitles for every used finance code (both years):")
print(confirmed.to_string(index=False))
"""
)

code(
    r"""
# Assert the dictionary agrees with the implemented crosswalk (keyword match on varTitle),
# and that every used column is present in all four finance tables.
EXPECTED_TITLE_KEYWORD = {
    "F1C011": "instruction", "F2E011": "instruction",
    "F1C021": "research",    "F2E021": "research",
    "F1C031": "public service", "F2E031": "public service",
    "F1C051": "academic support", "F2E041": "academic support",
    "F1C061": "student service",  "F2E051": "student service",
    "F1C071": "institutional support", "F2E061": "institutional support",
    "F1C191": "total expenses", "F2E131": "total expenses",
}
for _, r in confirmed.iterrows():
    kw = EXPECTED_TITLE_KEYWORD[r["varname"]]
    assert kw.lower() in r["varTitle"].lower(), (
        f"Dictionary disagrees for {r['varname']} ({r['label']}): "
        f"title={r['varTitle']!r} does not contain {kw!r}"
    )
cq.assert_finance_columns_present(con)
print("✓ Dictionary confirms the crosswalk; all finance function + total columns present in all 4 tables.")
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Step 3 — `hd_clean` (institution directory)

One row per `UNITID × year`, stacked from the 2012 + 2022 HD files via
`UNION ALL` with a literal `year`. Carries `instnm, stabbr, sector, control,
iclevel` — the state/sector dimensions every downstream join and chart needs.
HD `control` (1=public, 2=private-nonprofit, 3=private for-profit) also lets
`03-prepare` verify GASB rows are public and FASB rows are private-nonprofit.
"""
)

code(
    r"""
hd = cq.build_hd_clean(con)
cq.quality_report(hd, "hd_clean", con, required_columns=["unitid", "year", "stabbr", "control"])
cq.load_to_duckdb(hd, "hd_clean", con)
cq.save_interim(hd, cfg, "hd_clean.parquet")
print("Rows per year:", hd.groupby("year").size().to_dict())
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Step 4 — `finance_functions_clean` (the harmonized long spine)

The heart of the project. GASB (`F1C*`) and FASB (`F2E*`) expenses-by-function
are **melted into one shared 6-function schema** — `instruction, research,
public_service, academic_support, student_services, institutional_support` —
with every row tagged `control` (`public` for GASB, `private_np` for FASB) and
carrying the nominal `amount` plus the `source_col` it came from. All in DuckDB
SQL (a `UNION ALL` of per-standard `SELECT`s), reading **only** the numeric
`F1C*`/`F2E*` totals — never an `X*` imputation flag.

A sidecar **`finance_totals_clean`** keeps each standard's own grand total
(GASB `F1C191` / FASB `F2E131`, **not** `F2E071`) for the §10 reconciliation
check only — it is never charted and never used as a share denominator (the
single share denominator, built in `03-prepare`, is the in-pipeline sum of the
harmonized function totals; design §1.2 note 3).

**Caveat (carried forward):** GASB isolates operation-and-maintenance of plant
as its own function; FASB distributes it into the other functions. So the
harmonized functions are comparable only to within that O&M-allocation
difference, and O&M is deliberately excluded from the admin-vs-classroom
numerators.
"""
)

code(
    r"""
fin = cq.build_finance_functions_clean(con)
cq.quality_report(fin, "finance_functions_clean", con,
                  required_columns=["unitid", "year", "control", "function", "amount"])
cq.load_to_duckdb(fin, "finance_functions_clean", con)
cq.save_interim(fin, cfg, "finance_functions_clean.parquet")

# Spot-assert the crosswalk against known raw values (design §1.1 / §10).
def _amt(unitid, year, control, function):
    m = fin[(fin.unitid == unitid) & (fin.year == year) &
            (fin.control == control) & (fin.function == function)]
    return float(m["amount"].iloc[0])

gasb_instr = _amt(100654, 2022, "public", "instruction")       # F1C011
fasb_instr = _amt(100690, 2022, "private_np", "instruction")   # F2E011
print(f"GASB UNITID 100654 instruction (F1C011) = {gasb_instr:,.0f}")
print(f"FASB UNITID 100690 instruction (F2E011) = {fasb_instr:,.0f}")
assert gasb_instr == 34969711.0, gasb_instr
assert fasb_instr == 2518813.0, fasb_instr

# No cross-standard contamination: public rows -> F1*, private_np rows -> F2*.
bad = fin[((fin.control == "public") & (~fin.source_col.str.startswith("F1"))) |
          ((fin.control == "private_np") & (~fin.source_col.str.startswith("F2")))]
assert len(bad) == 0, f"cross-standard contamination in {len(bad)} rows"
print("✓ Crosswalk spot-values match; no cross-standard contamination.")
"""
)

code(
    r"""
# Per-sector × function × year nonzero coverage (design §10). Surfaces any
# reporting hole and documents that the CORRECTED academic_support (F1C051 /
# F2E041) is well-populated in BOTH sectors (the design's 'GASB-sparse' claim
# was the wrong column and no longer applies).
coverage = cq.run_sql(
    '''
    SELECT control, year, function,
           COUNT(*) FILTER (WHERE amount IS NOT NULL AND amount <> 0) AS nonzero,
           COUNT(*) AS total
    FROM finance_functions_clean
    GROUP BY control, year, function
    ORDER BY function, control, year
    ''', con)
print(coverage.to_string(index=False))

ac = coverage[coverage.function == "academic_support"]
print("\\nacademic_support coverage (corrected F1C051 / F2E041):")
print(ac.to_string(index=False))
"""
)

code(
    r"""
# Sidecar per-standard grand totals + FASB reconciliation check (design §10).
tot = cq.build_finance_totals_clean(con)
cq.quality_report(tot, "finance_totals_clean", con,
                  required_columns=["unitid", "year", "control", "raw_total"])
cq.load_to_duckdb(tot, "finance_totals_clean", con)
cq.save_interim(tot, cfg, "finance_totals_clean.parquet")

# FASB: F2E131 >= sum of the six function totals, for every FASB row.
recon = cq.run_sql(
    '''
    SELECT COUNT(*) AS n_rows,
           COUNT(*) FILTER (
             WHERE TRY_CAST(F2E131 AS DOUBLE) >= COALESCE(TRY_CAST(F2E011 AS DOUBLE),0)
                + COALESCE(TRY_CAST(F2E021 AS DOUBLE),0) + COALESCE(TRY_CAST(F2E031 AS DOUBLE),0)
                + COALESCE(TRY_CAST(F2E041 AS DOUBLE),0) + COALESCE(TRY_CAST(F2E051 AS DOUBLE),0)
                + COALESCE(TRY_CAST(F2E061 AS DOUBLE),0)
           ) AS n_total_ge_sum
    FROM ipeds_finance_fasb_2022_raw
    ''', con)
print(recon.to_string(index=False))
assert int(recon.n_rows.iloc[0]) == int(recon.n_total_ge_sum.iloc[0]), "FASB total < sum of functions"
print("✓ FASB total (F2E131) >= sum of function totals for all rows.")
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Step 5 — `fte_clean` (12-month FTE)

One row per `UNITID × year`: `fte_total = FTEUG + FTEGD` from the re-ingested
EFIA file (B1). `FTEGD` is null for institutions with no graduate programs, so
both terms are coalesced to 0. This is IPEDS's own authoritative 12-month FTE —
no headcount approximation (design §4). `03-prepare` divides each function
amount by `fte_total`; null/zero-FTE institutions are dropped from per-FTE views
there (reported), kept in absolute views.
"""
)

code(
    r"""
fte = cq.build_fte_clean(con)
cq.quality_report(fte, "fte_clean", con, required_columns=["unitid", "year", "fte_total"])
cq.load_to_duckdb(fte, "fte_clean", con)
cq.save_interim(fte, cfg, "fte_clean.parquet")

zero_fte = cq.run_sql(
    "SELECT year, COUNT(*) FILTER (WHERE fte_total IS NULL OR fte_total = 0) AS zero_or_null, "
    "COUNT(*) AS total FROM fte_clean GROUP BY year ORDER BY year", con)
print("FTE null/zero counts (dropped from per-FTE views in 03):")
print(zero_fte.to_string(index=False))
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Step 6 — `charges_clean` (sticker price)

One row per `UNITID × year` with the three undergraduate residency tiers. The
IC_AY dictionary mapping (design §7) is **`TUITION1` = in-district, `TUITION2` =
in-state, `TUITION3` = out-of-state**, with the matching `FEE1/2/3`. This is the
**published list price** and has a time series (2012 & 2022). It is kept
**DISTINCT** from Scorecard net price (next step) — the two are never combined.

> **⭐ 2012 now carries real tuition (upstream ingest fix).** The earlier
> `ipeds_charges_2012_raw` was malformed — a trailing comma in `ic2012_ay.csv`
> gave every row one more field than the header, so pandas' C parser promoted
> `UNITID` to the row index and shifted every labeled column left by one. Because
> IPEDS interleaves `X*` imputation-flag columns (holding `"R"`) with the data
> columns, `UNITID` absorbed the `"R"` flag and the real tuition landed in the
> adjacent flag column — the all-`"R"` symptom. `01-ingest` was repaired to read
> IC2012 with `index_col=False` (keeping UNITID as data, dropping the empty
> trailing field); 2022 was unaffected (no trailing comma). Re-running
> `build_charges_clean` here propagates the fix forward — **nothing in
> `charges_clean` is edited directly** — so the 2012 rows now carry real numeric
> `TUITION1/2/3` + `FEE1/2/3` instead of nulls.
"""
)

code(
    r"""
charges = cq.build_charges_clean(con)
cq.quality_report(charges, "charges_clean", con, required_columns=["unitid", "year"], max_null_pct=0.95)
cq.load_to_duckdb(charges, "charges_clean", con)
cq.save_interim(charges, cfg, "charges_clean.parquet")
print("Rows per year:", charges.groupby("year").size().to_dict())
print("Columns:", charges.columns.tolist())
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Step 7 — `net_price_clean` (Scorecard net price — kept DISTINCT)

One row per `UNITID` (a single most-recent-cohort **snapshot**, no `year`):
`net_price_pub` (`NPT4_PUB`), `net_price_priv` (`NPT4_PRIV`), `cost_attendance`
(`COSTT4_A`). This is **net price after grant aid** — what students actually pay
— and is a different quantity from sticker price. It lives in its own table and
is a present-day context layer only (not inflation-adjusted into the panel; §7).
"""
)

code(
    r"""
netp = cq.build_net_price_clean(con)
cq.quality_report(netp, "net_price_clean", con, required_columns=["unitid"], max_null_pct=0.95)
cq.load_to_duckdb(netp, "net_price_clean", con)
cq.save_interim(netp, cfg, "net_price_clean.parquet")
print("Non-null net price:",
      cq.run_sql("SELECT COUNT(net_price_pub) AS pub, COUNT(net_price_priv) AS priv FROM net_price_clean", con)
      .to_dict("records")[0])
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Step 8 — `cpi_clean` (inflation deflators)

One row per `year`: `cpi_all_items` (CUUR0000SA0) + `cpi_tuition_subindex`
(CUUR0000SEEB01), from the **M13 annual-average** rows. `cpi_u_raw.year` and
`.value` are stored as text, so we `TRY_CAST(year AS INTEGER)` /
`TRY_CAST(value AS DOUBLE)` before any filter (design §5). We then **assert an
M13 row exists for both 2012 and 2022 with a positive `cpi_all_items`** — failing
loudly otherwise, because without CY2022 the 2021-22 dollars can't be deflated.
All-Items is the only deflator; the tuition subindex is for the
tuition-vs-general-inflation comparison only (never deflates spending).
"""
)

code(
    r"""
cpi = cq.build_cpi_clean(con)
cq.quality_report(cpi, "cpi_clean", con, required_columns=["year", "cpi_all_items"], max_null_pct=0.5)
cq.load_to_duckdb(cpi, "cpi_clean", con)
cq.save_interim(cpi, cfg, "cpi_clean.parquet")

anchors = cpi[cpi.year.isin([2012, 2022])][["year", "cpi_all_items"]].set_index("year")["cpi_all_items"].to_dict()
print("CPI-U All-Items annual averages at the two anchor years:", anchors)
for y in (2012, 2022):
    assert y in anchors and anchors[y] and anchors[y] > 0, f"missing/invalid CPI All-Items for {y}"
print(f"✓ Deflator ready — 2012 dollars scale to 2022 by x{anchors[2022]/anchors[2012]:.4f}")
"""
)

# ===========================================================================
# REFRAME EXPANSION — clean Sources A–D into interim tables
# ===========================================================================
md(
    r"""
---
# ⭐ REFRAME EXPANSION — clean the four new sources (A–D)

Each new raw source (`nces_tuition_longrun_raw`, `delta_cost_raw`, the raw-IPEDS
finance tail, the IPEDS HR files) is harmonized here into interim `_clean` tables,
all in DuckDB SQL via `src/clean_quality.py` builders. Each passes
`quality_report()` before `save_interim()`. **The spending series use SHARES of
core functional spending with an identical in-pipeline denominator**, so the
honest finding — *non-instructional spending outgrew instruction, NOT admin
alone* — can be read straight from the clean tables.
"""
)

# --------------------------------------------------------------------------- A
md(
    r"""
## Step A — `tuition_longrun_clean` (deep tuition skyrocket, 1963-64 → latest)

`nces_tuition_longrun_raw` is already tidy-long from the ingest parser; this is a
light DuckDB typing/validation pass → one row per
**(academic_year × control × level × dollar_basis × cost_component)** with numeric
`value` and the constant-$ `base_year`. We assert the known anchors hold (public
4-yr tuition&fees ≈ \$243 in 1963-64, ≈ \$9,750 in 2022-23).
"""
)

code(
    r"""
tl = cq.build_tuition_longrun_clean(con)
cq.quality_report(tl, "tuition_longrun_clean", con,
                  required_columns=["year_start", "control", "value"], max_null_pct=0.6)
cq.load_to_duckdb(tl, "tuition_longrun_clean", con)
cq.save_interim(tl, cfg, "tuition_longrun_clean.parquet")

base_year = int(tl["base_year"].dropna().iloc[0])
print("constant-$ base year:", f"{base_year}-{str(base_year+1)[-2:]}")
pub4 = tl[(tl.control == "public") & (tl.level == "4-year")
          & (tl.cost_component == "tuition_fees") & (tl.dollar_basis == "current")]
a1963 = float(pub4[pub4.year_start == 1963].value.iloc[0])
a2022 = float(pub4[pub4.year_start == 2022].value.iloc[0])
print(f"anchor — public 4-yr t&f current: 1963-64 ${a1963:,.0f} (≈243), 2022-23 ${a2022:,.0f} (≈9,750)")
assert 230 <= a1963 <= 260, f"1963-64 anchor off: {a1963}"
assert 9000 <= a2022 <= 10500, f"2022-23 anchor off: {a2022}"
print("✓ tuition long-run anchors hold.")
"""
)

# --------------------------------------------------------------------------- B
md(
    r"""
## Step B — `delta_spending_clean` + `delta_spending_national_clean` (1987-2012)

From `delta_cost_raw` (public + private-nonprofit only; for-profits dropped),
build one row per **unitid × year × function** carrying nominal `amount`, Delta's
constructed 12-month `fte_total`, `amount_per_fte`, and the within-institution
**`share`** of core functional spending (denominator = sum over the six core
functions, computed identically everywhere). Then a national aggregate
(`delta_spending_national_clean`, one row per **year × function**) = summed-\$ /
summed-FTE and summed-share — the 1987→2012 trend backbone.

> Delta is a DERIVED product (Jaquette-Parra) and ends 2011-12 — SHARES are
> preferred over absolute per-FTE where imputation risk is higher.
"""
)

code(
    r"""
ds = cq.build_delta_spending_clean(con)
cq.quality_report(ds, "delta_spending_clean", con,
                  required_columns=["unitid", "year", "function", "amount"], max_null_pct=0.6)
cq.load_to_duckdb(ds, "delta_spending_clean", con)
cq.save_interim(ds, cfg, "delta_spending_clean.parquet")
print("delta_spending_clean:", ds.shape, "years", int(ds.year.min()), "->", int(ds.year.max()))

dn = cq.build_delta_spending_national_clean(con)
cq.quality_report(dn, "delta_spending_national_clean", con,
                  required_columns=["year", "function", "share"], max_null_pct=0.1)
cq.load_to_duckdb(dn, "delta_spending_national_clean", con)
cq.save_interim(dn, cfg, "delta_spending_national_clean.parquet")

print("\nNational SHARE of core spending, 1987 vs 2012 (the honest nuance):")
piv = dn.pivot_table(index="year", columns="function", values="share")
piv["non_instruction"] = piv[["student_services", "academic_support", "institutional_support"]].sum(axis=1)
print(piv.loc[[1987, 2012], ["instruction", "institutional_support", "academic_support",
                             "student_services", "non_instruction"]].round(3).to_string())
"""
)

# --------------------------------------------------------------------------- C
md(
    r"""
## Step C — `finance_tail_clean` + `spending_mix_clean` (extend to the present, seam at 2012)

For each raw-IPEDS finance-tail year ingested (2016, 2019), melt GASB (F1C\*) +
FASB (F2E\*) function totals onto the **same** harmonized category labels as
Delta, join EFIA 12-month FTE, and compute per-FTE + the core-spending SHARE with
the identical in-pipeline denominator — so the raw tail stacks cleanly onto the
Delta series. Then `spending_mix_clean` = **Delta national (1987-2012) UNION the
raw-tail national (2013+)**, one row per **year × function** with a `source` seam
flag (`delta` / `ipeds_raw`). **Footnote the 2012 seam on every chart using it.**
"""
)

code(
    r"""
from src.clean_quality import FUNCTION_CROSSWALK

# Which finance-tail years actually landed in 01-ingest (defensive — Source C may
# have dropped a year).
TAIL_YEARS = [y for y in (2016, 2019)
              if f"ipeds_finance_gasb_{y}_raw" in {t[0] for t in con.execute("SHOW TABLES").fetchall()}]
print("finance-tail years present:", TAIL_YEARS)
assert TAIL_YEARS, "no finance-tail years available — Source C ingest missing"

ft = cq.build_finance_tail_clean(con, TAIL_YEARS, FUNCTION_CROSSWALK)
cq.quality_report(ft, "finance_tail_clean", con,
                  required_columns=["unitid", "year", "function", "amount"], max_null_pct=0.6)
cq.load_to_duckdb(ft, "finance_tail_clean", con)
cq.save_interim(ft, cfg, "finance_tail_clean.parquet")
print("finance_tail_clean:", ft.shape, "years", sorted(ft.year.unique().tolist()))

mix = cq.build_spending_mix_clean(con)
cq.quality_report(mix, "spending_mix_clean", con,
                  required_columns=["year", "function", "share", "source"], max_null_pct=0.1)
cq.load_to_duckdb(mix, "spending_mix_clean", con)
cq.save_interim(mix, cfg, "spending_mix_clean.parquet")
print("\nspending_mix_clean: years", int(mix.year.min()), "->", int(mix.year.max()),
      "| sources", sorted(mix.source.unique().tolist()))
"""
)

# --------------------------------------------------------------------------- D
md(
    r"""
## Step D — `hr_staff_clean` + `hr_staff_national_clean` (admin vs faculty headcount, 2013→2022)

For each IPEDS HR year (2013, 2016, 2019, 2022), aggregate staff headcount into
**`admin_headcount`** (STAFFCAT 1300 = Management, FTPT=1) and
**`faculty_headcount`** (STAFFCAT 1210 = Instructional staff, FTPT=1), one row per
**unitid × year**, joined to EFIA 12-month FTE. Then a national aggregate
(`hr_staff_national_clean`, one row per **year**) with summed headcounts, FTE, and
**`admin_per_100_faculty`**.

> ⭐ 2012-13 SOC-category break — this series is clean only from 2012-13 forward;
> no pre-2012 crosswalk. Footnote the break on every chart using it.
"""
)

code(
    r"""
HR_YEARS = [y for y in (2013, 2016, 2019, 2022)
            if f"ipeds_hr_{y}_raw" in {t[0] for t in con.execute("SHOW TABLES").fetchall()}]
print("HR years present:", HR_YEARS)
assert HR_YEARS, "no HR years available — Source D ingest missing"

hr = cq.build_hr_staff_clean(con, HR_YEARS)
cq.quality_report(hr, "hr_staff_clean", con,
                  required_columns=["unitid", "year", "admin_headcount", "faculty_headcount"],
                  max_null_pct=0.6)
cq.load_to_duckdb(hr, "hr_staff_clean", con)
cq.save_interim(hr, cfg, "hr_staff_clean.parquet")

hn = cq.build_hr_staff_national_clean(con)
cq.quality_report(hn, "hr_staff_national_clean", con,
                  required_columns=["year", "admin_headcount", "faculty_headcount"], max_null_pct=0.1)
cq.load_to_duckdb(hn, "hr_staff_national_clean", con)
cq.save_interim(hn, cfg, "hr_staff_national_clean.parquet")

print("\nNational admin vs faculty headcount + FTE, by year:")
print(hn.round(1).to_string(index=False))
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Step 9 — Carry caveats into `_sources` + `SOURCES.md`

The harmonized `_clean` tables get `_sources` rows recording the methodology and
series-break caveats so they reach chart footnotes downstream: the GASB/FASB
O&M-allocation difference (the primary comparability caveat), the
dictionary-correction (GASB functions are `F1C*`, not `F1E*`; FASB total is
`F2E131`, not `F2E071`), the IPEDS 2012↔2022 series break, and institution
enter/exit between years. (`SOURCES.md` carries the same notes in prose.)
"""
)

code(
    r"""
HARMONIZED_METHOD = (
    "Harmonized GASB (public, F1C* expense-by-function block) and FASB (private "
    "nonprofit, F2E* block) onto one shared 6-function schema (instruction, research, "
    "public_service, academic_support, student_services, institutional_support), each "
    "row tagged control. GASB function codes dictionary-confirmed as F1C011/021/031/051/"
    "061/071 (the draft's F1E01-07 are the scholarships/grants block, not functions). "
    "Admin = institutional support only (F1C071 / F2E061). Per-standard grand totals "
    "(GASB F1C191 / FASB F2E131, never F2E071) kept in finance_totals_clean for "
    "reconciliation only; the share denominator is the in-pipeline function sum."
)
HARMONIZED_BREAKS = (
    "GASB isolates operation-and-maintenance of plant as its own function while FASB "
    "distributes it into the other functions, so harmonized functions are comparable only "
    "to within that O&M-allocation difference and raw totals are never compared across "
    "standards. IPEDS finance definitions shifted 2011-12 vs 2021-22 (two series, not a "
    "continuous panel; subcomponent column sets changed, so only stable function-total "
    "codes are used). Institutions enter/exit between 2012 and 2022 (HD 7,735 -> 6,256)."
)
for t in ["finance_functions_clean", "finance_totals_clean"]:
    cq.register_source(
        con, table=t, name="IPEDS Finance GASB+FASB (harmonized, NCES)",
        url="https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx",
        license="Public domain (U.S. federal government work)",
        notes="Harmonized expenses-by-function spine for the admin-vs-classroom analysis.",
        retrieved=RETRIEVED, methodology=HARMONIZED_METHOD, series_breaks=HARMONIZED_BREAKS,
    )
cq.register_source(
    con, table="hd_clean", name="IPEDS Institutional Characteristics (NCES)",
    url="https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx",
    license="Public domain (U.S. federal government work)",
    notes="Institution directory (state, sector, control, level) stacked for 2012 + 2022.",
    retrieved=RETRIEVED,
    methodology="HD header stacked across the two collection years with a literal year column.",
    series_breaks="Institutions enter/exit between 2012 and 2022; over-time aggregates note the changing set.",
)
cq.register_source(
    con, table="fte_clean", name="IPEDS 12-month FTE (EFIA, NCES)",
    url="https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx",
    license="Public domain (U.S. federal government work)",
    notes="fte_total = FTEUG + FTEGD (reported 12-month undergraduate + graduate FTE).",
    retrieved=RETRIEVED,
    methodology="Authoritative IPEDS 12-month FTE; no headcount approximation (EFFY has no FTE).",
    series_breaks="IPEDS definitions shifted 2011-12 vs 2021-22.",
)
cq.register_source(
    con, table="charges_clean", name="IPEDS Charges / sticker price (IC_AY, NCES)",
    url="https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx",
    license="Public domain (U.S. federal government work)",
    notes="Published tuition & required fees. TUITION1=in-district, 2=in-state, 3=out-of-state (+FEE1/2/3).",
    retrieved=RETRIEVED, methodology="Sticker/list price; kept distinct from Scorecard net price.",
    series_breaks="Sticker != net price (reported separately). IPEDS 2012 vs 2022 definition shifts.",
)
cq.register_source(
    con, table="net_price_clean", name="College Scorecard net price (Dept. of Education)",
    url="https://collegescorecard.ed.gov/data/",
    license="Public domain (U.S. federal government work)",
    notes="Average net price after grant aid (NPT4_PUB/NPT4_PRIV) + cost of attendance (COSTT4_A).",
    retrieved=RETRIEVED, methodology="Most-recent-cohort snapshot; net price, NOT sticker price.",
    series_breaks="Single latest-cohort snapshot, not a time series; not inflation-adjusted into the panel.",
)
cq.register_source(
    con, table="cpi_clean", name="BLS CPI-U annual averages (All Items + tuition subindex)",
    url=cfg["sources"]["cpi_u"]["api_url"], license="Public domain (U.S. federal government work)",
    notes="M13 annual averages. cpi_all_items = deflator; cpi_tuition_subindex = comparison only.",
    retrieved=RETRIEVED, methodology="BLS public API; deflate to constant 2022 dollars with All-Items.",
    series_breaks="CPI-U base 1982-84=100, NSA; used only as a ratio.",
)
print("Registered _sources for all 7 _clean tables.")
cq.get_sources(con)[["duckdb_table", "source_name"]]
"""
)

code(
    r"""
# REFRAME EXPANSION — _sources rows for the four new source families' _clean tables.
cq.register_source(
    con, table="tuition_longrun_clean",
    name="NCES Digest Table 330.10 (tidy long)",
    url="https://nces.ed.gov/programs/digest/d24/tables/dt24_330.10.asp",
    license="Public domain (U.S. federal government work)",
    notes="Tidy-long national tuition/fees/room/board by control×level×dollar-basis×component, 1963-64 -> latest.",
    retrieved=RETRIEVED,
    methodology="Light DuckDB typing of the already-long NCES 330.10 parse; constant-$ base = the Digest edition's base year.",
    series_breaks=("National averages, not per-institution; room/board basis + institution universe shifted "
                   "across Digest editions; constant-$ uses CPI-U All-Items (general, not tuition-specific); "
                   "published (sticker) price, not net-of-aid."),
)
for t, nm, note in [
    ("delta_spending_clean", "Delta Cost Project spending-by-function (per-institution)",
     "unitid×year×function nominal $, per-FTE, and within-institution SHARE of core spending, public+private-nonprofit, 1987-2012."),
    ("delta_spending_national_clean", "Delta Cost Project spending-by-function (national)",
     "year×function national summed-$/summed-FTE per-FTE and national SHARE, 1987-2012 — the trend backbone."),
]:
    cq.register_source(
        con, table=t, name=nm,
        url="https://nces.ed.gov/ipeds/use-the-data/delta-cost-project-finance-data",
        license="Public domain (U.S. federal government work)", notes=note, retrieved=RETRIEVED,
        methodology=("NCES-harmonized CFI-method function totals (instruction01/research01/pubserv01/"
                     "acadsupp01/studserv01/instsupp01) ÷ Delta constructed FTE; SHARE denominator = "
                     "in-pipeline sum of the six core functions. Admin = institutional support only."),
        series_breaks=("Delta is a DERIVED/imputed product (Jaquette & Parra); harmonizes FASB-1997/"
                       "GASB-2002-04/Aligned-Form-2008-10 but ENDS 2011-12 (seam to the raw tail at 2012). "
                       "Prefer SHARES over absolute per-FTE."),
    )
cq.register_source(
    con, table="finance_tail_clean", name="Raw IPEDS finance tail (harmonized onto Delta categories)",
    url="https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx",
    license="Public domain (U.S. federal government work)",
    notes="Raw IPEDS GASB(F1C*)+FASB(F2E*) 2013-2021 melted onto Delta's category labels, per-FTE + core SHARE.",
    retrieved=RETRIEVED,
    methodology="Same crosswalk/denominator as the finance spine; EFIA 12-month FTE denominator; O&M excluded.",
    series_breaks="Seam at 2011-12 (Delta ends, raw IPEDS tail begins). GASB isolates O&M; FASB distributes it.",
)
cq.register_source(
    con, table="spending_mix_clean", name="Stacked national spending-by-function series (1987 -> latest)",
    url="https://nces.ed.gov/ipeds/use-the-data/delta-cost-project-finance-data",
    license="Public domain (U.S. federal government work)",
    notes=("Delta national (1987-2012) UNION raw-IPEDS national (2013+), year×function with per_fte, share, "
           "and a source seam flag. The table the spending-mix chart consumes."),
    retrieved=RETRIEVED,
    methodology="National summed-$/summed-FTE and summed-share; identical core-function denominator across the seam.",
    series_breaks=("⭐ Seam at 2012 (source='delta' before, 'ipeds_raw' after). Honest reading: NON-"
                   "INSTRUCTIONAL spending (student services + academic support + institutional support) "
                   "outgrew instruction; institutional support (admin) ALONE is roughly flat."),
)
for t, nm, note in [
    ("hr_staff_clean", "IPEDS HR admin vs faculty headcount (per-institution)",
     "unitid×year admin_headcount (Management, STAFFCAT 1300) + faculty_headcount (Instructional, 1210) + EFIA FTE, 2013-2022."),
    ("hr_staff_national_clean", "IPEDS HR admin vs faculty headcount (national)",
     "year summed admin/faculty headcount + FTE + admin_per_100_faculty, 2013-2022."),
]:
    cq.register_source(
        con, table=t, name=nm,
        url="https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx",
        license="Public domain (U.S. federal government work)", notes=note, retrieved=RETRIEVED,
        methodology="IPEDS Human Resources occupational categories (FTPT=1 all-staff HRTOTLT); EFIA FTE denominator.",
        series_breaks=("⭐ HARD 2012-13 SOC-category break — clean only from 2012-13 forward; NO pre-2012 "
                       "crosswalk. Over-time comparisons start at 2013."),
    )
print("Registered _sources for the 7 reframe-expansion _clean tables.")
"""
)

# ---------------------------------------------------------------------------
md(
    """
## Verify — interim artifacts + `_clean` tables

Confirm every interim Parquet file was written and every `_clean` DuckDB table
exists with the expected row count.
"""
)

code(
    r"""
INTERIM = ["hd_clean", "finance_functions_clean", "finance_totals_clean",
           "fte_clean", "charges_clean", "net_price_clean", "cpi_clean",
           "cpi_sectors_clean",
           # REFRAME EXPANSION — the four new source families.
           "tuition_longrun_clean",
           "delta_spending_clean", "delta_spending_national_clean",
           "finance_tail_clean", "spending_mix_clean",
           "hr_staff_clean", "hr_staff_national_clean"]
interim_dir = Path(cfg["paths"]["data_interim"])
print(f"{'table':<28}{'parquet?':<10}{'db rows':>10}")
print("-" * 48)
for t in INTERIM:
    pq = interim_dir / f"{t}.parquet"
    assert pq.exists(), f"missing interim parquet: {pq}"
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"{t:<28}{'yes':<10}{n:>10,}")
print(f"\\nAll {len(INTERIM)} interim Parquet files written and all {len(INTERIM)} _clean tables created.")
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
**Next:** `03-prepare.ipynb` — join the harmonized finance spine to `hd_clean` +
`fte_clean`, normalize per 12-month FTE, deflate to constant-2022 dollars with
`cpi_clean`, build the chart-ready `chart_*` tables, and export the
`higher_education_cost_v1` package with a codebook.
"""
)

# ---------------------------------------------------------------------------
nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}

out = Path("notebooks/02-clean.ipynb")
nbf.write(nb, str(out))
print("Wrote", out, "with", len(cells), "cells")
