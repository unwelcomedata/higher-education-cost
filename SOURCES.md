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

> The entries below are the **planned** primary sources for this project.
> Confirm the exact per-year download URLs and file structures during
> `01-ingest` before treating any of these as final, and fill in the
> `Retrieved` date when each file actually lands in `data/raw/`.

### IPEDS — Integrated Postsecondary Education Data System
- **Publisher:** National Center for Education Statistics (NCES), U.S. Department of Education
- **URL:** https://nces.ed.gov/ipeds/use-the-data — complete data files at https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx
- **Format:** CSV / ZIP (per survey, per year)
- **License:** Public domain (U.S. federal government work)
- **Fields used:** Institutional Characteristics (state, sector, level, Carnegie class); Charges (published tuition & fees); Finance/F survey (expenses by function — instruction, academic support, student services, institutional support, research); Enrollment (EF/EFFY, for per-FTE normalization)
- **Coverage:** U.S. postsecondary institutions; ~1980–present depending on survey component
- **Notes:** Finance survey splits into GASB (public) and FASB (private nonprofit/for-profit) files with different accounting standards — expense categories do NOT map 1:1 and must be harmonized or analyzed separately. Survey definitions have changed over the decades; watch for series breaks.
- **Retrieved:** TODO

### College Scorecard
- **Publisher:** U.S. Department of Education
- **URL:** https://collegescorecard.ed.gov/data/
- **Format:** CSV (bulk ZIP) + API
- **License:** Public domain (U.S. federal government work)
- **Fields used:** Net price, average cost of attendance, completion rate, post-enrollment earnings, by institution and year
- **Coverage:** U.S. Title IV institutions; ~1996–present (cost/net-price fields robust from ~2009)
- **Notes:** Used for the modern cost-and-outcomes layer and to cross-validate IPEDS cost figures. Net price ≠ sticker price — report both explicitly.
- **Retrieved:** TODO

### BLS Consumer Price Index (CPI-U)
- **Publisher:** U.S. Bureau of Labor Statistics
- **URL:** https://download.bls.gov/pub/time.series/cu/
- **Format:** Tab-separated flat files
- **License:** Public domain (U.S. federal government work)
- **Fields used:** CPI-U All Items (for real-dollar adjustment); optionally the college-tuition subindex (SEEB01) to compare tuition inflation vs general inflation
- **Coverage:** U.S., monthly, 1913–present (All Items)
- **Notes:** Nominal tuition growth is misleading; inflation-adjustment is required for the core "cost over time" story.
- **Retrieved:** TODO

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
