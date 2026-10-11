# Data Sources — higher-education-cost

All data used in this project is from authoritative sources. Crowd-edited
references (Wikipedia, etc.) are not used as primary sources.

Document every data source here before ingesting it. Include enough detail
that someone else could independently locate and verify the original data.

---

## Source Template

Copy and fill in for each source:

### [Source Name]
- **Publisher:** [Agency, organization, or author]
- **URL:** [Direct link to the file or page]
- **Format:** [CSV | JSON | HTML table | ZIP | PDF | hand-curated]
- **License:** [Public domain | CC0 | CC-BY | proprietary | etc.]
- **Fields used:** [Column names or description of what was extracted]
- **Coverage:** [Geographic scope, date range, or other relevant bounds]
- **Notes:** [Any caveats, known issues, or methodology notes]
- **Retrieved:** [YYYY-MM-DD]

---

## Sources

> The URLs and structure below were **confirmed live during `01-ingest` on
> 2026-09-30**. Two IPEDS collection years (2011-12 and 2021-22) were pulled to
> support the over-time story; `01-ingest.ipynb` narrates every download.

### IPEDS — Integrated Postsecondary Education Data System
- **Publisher:** National Center for Education Statistics (NCES), U.S. Department of Education
- **URL:** Complete data files at https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx — per-survey, per-year zipped CSVs at the stable pattern `https://nces.ed.gov/ipeds/datacenter/data/<SURVEY_FILE>.zip`
- **Format:** ZIP of CSV (one per survey component, per collection year)
- **License:** Public domain (U.S. federal government work)
- **Fields used / files pulled (2011-12 and 2021-22):**
  - `HD<year>` — Institutional Characteristics header (state `STABBR`, sector, level, Carnegie class); keys other tables via `UNITID`
  - `IC<year>_AY` — Charges: published tuition & required fees (sticker price), academic-year
  - `F<yy><yy>_F1A` — Finance **GASB** (public institutions): expenses by function
  - `F<yy><yy>_F2` — Finance **FASB** (private nonprofit): expenses by function
  - `EFFY<year>` — 12-month unduplicated enrollment (for per-FTE normalization)
- **Coverage:** U.S. postsecondary institutions; this ingest pulls collection years 2011-12 and 2021-22 (a full decade)
- **Notes:** **The Finance survey splits into GASB (public, `*_F1A`) and FASB (private nonprofit, `*_F2`) files with different accounting standards — expense-function categories do NOT map 1:1 and are kept as separate raw tables (`ipeds_finance_gasb_*`, `ipeds_finance_fasb_*`); they must be harmonized before any admin-vs-classroom comparison.** IPEDS survey definitions have also shifted over the decade, so 2011-12 and 2021-22 are treated as separate series requiring harmonization. IPEDS CSVs read as `latin-1` (occasional non-UTF-8 bytes in text fields) and with `index_col=False` (see IC2012 note).
- **File-variant note (`IC2012_AY`):** the base `IC2012_AY.zip` → `ic2012_ay.csv` is the correct file (no `_rv` revised variant needed), but its **header has 268 names while every data row has 269 fields** — the rows carry a trailing comma / extra unnamed empty field. Pandas' default parser responds to `fields > header` by promoting column 0 to the row index, which shifted every labeled column one position left and left `UNITID` and all tuition values holding the interleaved `X`-prefixed imputation flags (literal `"R"`). Reading with `index_col=False` keeps `UNITID` as data and drops the trailing empty field, parsing the file correctly. `IC2022_AY` has matching 235-name/235-field rows and is unaffected (the fix is a no-op for it). The raw ZIP on disk is kept verbatim; only the parse was corrected.
- **Retrieved:** 2026-09-30

### College Scorecard
- **Publisher:** U.S. Department of Education
- **URL:** Data page https://collegescorecard.ed.gov/data/ — bulk "Most Recent Institution-Level Data" ZIP at `https://ed-public-download.scorecard.network/downloads/Most-Recent-Cohorts-Institution_05192025.zip`
- **Format:** CSV inside a bulk ZIP
- **License:** Public domain (U.S. federal government work)
- **Fields used:** Net price (`NPT4_*`), cost of attendance (`COSTT4_*`), completion rate (`C150_*`), median post-enrollment earnings (`MD_EARN_*`), by institution
- **Coverage:** U.S. Title IV institutions; most-recent cohort snapshot (cost/net-price fields robust from ~2009)
- **Notes:** The historical bulk host `ed-public-download.app.cloud.gov/downloads/CollegeScorecard_Raw_Data.zip` now returns **404**; the current host `ed-public-download.scorecard.network` was resolved from the data.ed.gov CKAN package listing (`college-scorecard-all-data-files`). This ingest uses the single-CSV "Most Recent Institution-Level Data" file (latest cohort per institution), not the full multi-year raw archive (`College_Scorecard_Raw_Data_05192025.zip`, documented in config for later use). Net price ≠ sticker price — report both explicitly.
- **Retrieved:** 2026-09-30

### BLS Consumer Price Index (CPI-U)
- **Publisher:** U.S. Bureau of Labor Statistics
- **URL:** BLS public timeseries API `https://api.bls.gov/publicAPI/v2/timeseries/data/` (see Notes on the flat-file host)
- **Format:** JSON (API) → saved as long-format CSV in `data/raw/cpi_u/`
- **License:** Public domain (U.S. federal government work)
- **Fields used:** `CUUR0000SA0` (CPI-U All Items, U.S. city average, NSA — real-dollar deflator); `CUUR0000SEEB01` (CPI-U college tuition & fees subindex, to compare tuition inflation vs general inflation). Pulled 2000–2024, monthly + M13 annual averages.
- **Coverage:** U.S., monthly, 1913–present (All Items); this ingest pulls 2000–2024
- **Notes:** **The flat-file host `https://download.bls.gov/pub/time.series/cu/` returns HTTP 403 (Akamai block page) to automated GETs — confirmed 2026-09-30 even with a full browser header set — so CPI-U is pulled from the BLS public API instead.** The API is keyless for modest use (25 requests/day, ≤10 years per request; the 2000–2024 span is fetched in two windows); an optional `BLS_API_KEY` in the gitignored `.env` raises the limits but is not required. CPI-U reference base is 1982-84=100; NSA (do not mix with seasonally adjusted). Nominal tuition growth is misleading; inflation adjustment is required for the "cost over time" story.
- **Retrieved:** 2026-09-30

#### IPEDS 12-month FTE (EFIA) — re-ingested in 02-clean
- **Publisher:** NCES, U.S. Dept. of Education. **URL:** `https://nces.ed.gov/ipeds/datacenter/data/EFIA<year>.zip`. **License:** public domain.
- **Fields used:** `FTEUG` (reported 12-month undergraduate FTE) + `FTEGD` (reported 12-month graduate FTE); one row per `UNITID`. **Why re-ingested:** the originally-loaded EFFY file carries 12-month *headcount* only — no FTE and no full-time/part-time split — so there is no viable FTE approximation. EFIA is IPEDS's own authoritative 12-month FTE, required for the per-FTE metric. Lands as `ipeds_fte_2012_raw` / `ipeds_fte_2022_raw`; `fte_clean` computes `fte_total = FTEUG + FTEGD`.
- **Retrieved:** 2026-09-30 (re-ingest).

#### Supplemental (validation / context)
- **NCES Digest of Education Statistics** — pre-tabulated national/state summary tables (https://nces.ed.gov/programs/digest/) — for cross-checking IPEDS-derived numbers.
- **SHEEO State Higher Education Finance (SHEF)** — state appropriations & public funding per FTE over time (https://shef.sheeo.org/) — adds the "who pays" (state support vs tuition) dimension.

---

## Harmonization & series-break caveats (settled in 02-clean)

Carried forward into chart footnotes and the `_sources` `methodology` /
`series_breaks` columns for the harmonized tables.

- **⭐ GASB expenses-by-function live in the `F1C` block, not `F1E`.** The
  harmonization design draft mapped GASB functions to `F1E01…F1E07`; the IPEDS
  **F1A data dictionary** (both collection years) shows those are the
  **scholarships / grants** block (Pell grants, state grants, …), *not* expenses
  by function. The dictionary-confirmed GASB function block is **`F1C`**:
  `F1C011` instruction, `F1C021` research, `F1C031` public service, `F1C051`
  academic support, `F1C061` student services, `F1C071` **institutional support
  (= admin)**, `F1C191` total expenses. FASB uses `F2E011…F2E061` (+ `F2E131`
  total — **not** `F2E071`, which is a function line). "Admin" = institutional
  support only (`F1C071` / `F2E061`).
- **Academic support is NOT GASB-sparse.** The design flagged GASB academic
  support as sparse (≈236/2,004) and excluded it from cross-sector comparison —
  but that was the wrong column (`F1E04` = local-government grants). The correct
  `F1C051` is well-populated in both sectors (≈1,875/2,004 in 2012; 1,825/1,936
  in 2022), on par with FASB `F2E041`. The "sparse" rationale is therefore
  defunct; whether to use academic support in public-vs-private charts is decided
  in `03-prepare`.
- **GASB vs FASB operation-and-maintenance (O&M) of plant.** GASB isolates O&M as
  its own function; FASB distributes it into the other functions. The harmonized
  functions are comparable only to within that allocation difference; O&M is
  deliberately excluded from the admin-vs-classroom numerators, and per-standard
  raw totals (GASB `F1C191` / FASB `F2E131`) are never compared across standards
  or used as a share denominator (the share denominator, built in `03-prepare`,
  is the in-pipeline sum of the harmonized function totals).
- **IPEDS 2011-12 vs 2021-22 is a series break, not a continuous panel.** Finance
  subcomponent column sets changed across the decade (GASB 322→288 cols, FASB
  394→340); only the stable function-total codes are used. Institutions enter and
  exit between the two years (HD 7,735 → 6,256), so over-time aggregates note the
  changing institution set.
- **CPI-U re-pulled through 2024.** The first ingest truncated `cpi_u_raw` at
  2019 (keyless BLS API ≤10 years/request); 02-clean re-pulls `CUUR0000SA0` +
  `CUUR0000SEEB01` across three ≤10-year windows so an M13 annual-average exists
  for 2022. Spending is deflated to **constant 2022 dollars** with All-Items
  only; the tuition subindex is for the tuition-vs-general-inflation comparison
  and never deflates spending.

---

## Notes on Data Quality

- All source files are saved verbatim to `data/raw/` and never modified.
- Discrepancies between sources should be noted here and resolved explicitly.

---

## Source Provenance in DuckDB

Every table in `data/project.duckdb` has a corresponding entry in the
`_sources` metadata table:

```sql
SELECT * FROM _sources;
```
