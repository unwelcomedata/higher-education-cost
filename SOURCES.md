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
- **Notes:** **The Finance survey splits into GASB (public, `*_F1A`) and FASB (private nonprofit, `*_F2`) files with different accounting standards — expense-function categories do NOT map 1:1 and are kept as separate raw tables (`ipeds_finance_gasb_*`, `ipeds_finance_fasb_*`); they must be harmonized before any admin-vs-classroom comparison.** IPEDS survey definitions have also shifted over the decade, so 2011-12 and 2021-22 are treated as separate series requiring harmonization. IPEDS CSVs read as `latin-1` (occasional non-UTF-8 bytes in text fields).
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

#### Supplemental (validation / context)
- **NCES Digest of Education Statistics** — pre-tabulated national/state summary tables (https://nces.ed.gov/programs/digest/) — for cross-checking IPEDS-derived numbers.
- **SHEEO State Higher Education Finance (SHEF)** — state appropriations & public funding per FTE over time (https://shef.sheeo.org/) — adds the "who pays" (state support vs tuition) dimension.

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
