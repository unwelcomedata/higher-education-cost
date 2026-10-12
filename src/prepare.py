"""Sellable dataset preparation and export utilities.

Takes a processed DataFrame and packages it for sale/distribution:
  - Drops any PII columns listed in config.yaml
  - Exports to CSV, Excel, and/or Parquet
  - Generates a plain-text codebook (column descriptions)

Usage in a notebook:
    from src.prepare import package_dataset
    package_dataset(df, cfg, name="my_dataset", codebook={"col": "description"})
"""

from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# PII stripping
# ---------------------------------------------------------------------------

def strip_pii(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Drop columns listed under export.strip_pii_columns in config.yaml."""
    cols_to_drop = cfg.get("export", {}).get("strip_pii_columns", [])
    if cols_to_drop:
        existing = [c for c in cols_to_drop if c in df.columns]
        if existing:
            df = df.drop(columns=existing)
            print(f"Stripped PII columns: {existing}")
    return df


# ---------------------------------------------------------------------------
# Codebook
# ---------------------------------------------------------------------------

def build_codebook(
    df: pd.DataFrame,
    descriptions: dict[str, str] | None = None,
    project_name: str = "",
    notes: str = "",
) -> str:
    """Generate a plain-text codebook for the dataset.

    Args:
        df:           The export-ready DataFrame.
        descriptions: Dict mapping column name → human-readable description.
                      Columns not in the dict get a placeholder.
        project_name: Printed in the header.
        notes:        Free-text notes appended at the bottom (source info, license, etc.).

    Returns:
        Codebook as a string (written to a .md file by package_dataset).
    """
    descriptions = descriptions or {}
    today = date.today().isoformat()

    lines = [
        f"# {project_name} — Dataset Codebook",
        f"Generated: {today}",
        "",
        "## Columns",
        "",
    ]

    for col in df.columns:
        dtype = str(df[col].dtype)
        desc = descriptions.get(col, "_No description provided._")
        non_null = df[col].notna().sum()
        total = len(df)
        lines.append(f"### `{col}`")
        lines.append(f"- **Type**: `{dtype}`")
        lines.append(f"- **Non-null**: {non_null:,} / {total:,} ({non_null/total:.1%})")
        lines.append(f"- **Description**: {desc}")
        lines.append("")

    if notes:
        lines += ["## Notes", "", textwrap.dedent(notes).strip(), ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def package_dataset(
    df: pd.DataFrame,
    cfg: dict[str, Any],
    name: str,
    codebook: dict[str, str] | None = None,
    notes: str = "",
    formats: list[str] | None = None,
) -> dict[str, Path]:
    """Strip PII, export to configured formats, and write a codebook.

    Args:
        df:       Processed DataFrame ready for packaging.
        cfg:      Loaded config dict.
        name:     Base filename (no extension).
        codebook: Column description dict passed to build_codebook().
        notes:    Free-text appended to the codebook (source, license, etc.).
        formats:  Override config export.formats. Supported: csv, xlsx, parquet.

    Returns:
        Dict of {format: Path} for every file written.
    """
    df = strip_pii(df, cfg)

    export_dir = Path(cfg["paths"]["export"])
    export_dir.mkdir(parents=True, exist_ok=True)

    export_cfg = cfg.get("export", {})
    active_formats = formats or export_cfg.get("formats", ["csv"])
    include_codebook = export_cfg.get("include_codebook", True)
    project_name = cfg.get("project_name", name)

    written: dict[str, Path] = {}

    if "csv" in active_formats:
        p = export_dir / f"{name}.csv"
        df.to_csv(p, index=False, encoding=cfg["settings"]["encoding"])
        written["csv"] = p
        print(f"Exported CSV     → {p}")

    if "xlsx" in active_formats:
        p = export_dir / f"{name}.xlsx"
        with pd.ExcelWriter(p, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="data")
        written["xlsx"] = p
        print(f"Exported Excel   → {p}")

    if "parquet" in active_formats:
        p = export_dir / f"{name}.parquet"
        df.to_parquet(p, index=False, engine=cfg["settings"]["parquet_engine"])
        written["parquet"] = p
        print(f"Exported Parquet → {p}")

    if include_codebook:
        cb_text = build_codebook(df, descriptions=codebook, project_name=project_name, notes=notes)
        cb_path = export_dir / f"{name}_codebook.md"
        cb_path.write_text(cb_text, encoding="utf-8")
        written["codebook"] = cb_path
        print(f"Wrote codebook   → {cb_path}")

    print(f"\n✓  Package complete: {len(df):,} rows × {len(df.columns)} columns")
    return written


# ---------------------------------------------------------------------------
# Quick summary helpers (useful before packaging)
# ---------------------------------------------------------------------------

# ===========================================================================
# Project-specific shaping helpers — higher-education-cost (03-prepare)
# ===========================================================================
#
# 03-prepare has TWO jobs: (1) build the chart-ready / analysis-ready processed
# tables for the "admin vs classroom, over time" story FROM the interim _clean
# tables, and (2) export the sellable package. Everything below is DuckDB-SQL
# based (no pandas chained transforms); each builder reads the _clean tables and
# returns a DataFrame the notebook saves via save_processed() + load_to_duckdb().
#
# Settled methodology (artifacts/HARMONIZATION-DESIGN.md), implemented here:
#   • "admin" = IPEDS Institutional support ONLY (function = institutional_support).
#   • Everything per 12-month FTE (fte_total from fte_clean), real constant-2022-$
#     via CPI-U All-Items (cpi_clean), base year 2022.
#   • control stays a dimension on every row (public / private_np); the two
#     sectors are shown together or split, never silently pooled.
#   • The share denominator is the IN-PIPELINE sum of the harmonized function
#     totals (design §1.2 note 3) — never a raw IPEDS total line.
#
# control codes: finance_functions_clean.control is 'public' (GASB) / 'private_np'
# (FASB); hd_clean.control is 1=public, 2=private-nonprofit, 3=for-profit.

from src.clean_quality import run_sql  # noqa: E402  (project helper, DuckDB-SQL)

# The comparable cross-sector core + context functions that form the single
# §1.2-note-3 share denominator (identical construction per sector). academic_support
# is EXCLUDED from this denominator so the denominator is identical in both sectors
# and a sector-asymmetric function can never move a cross-sector share.
_SHARE_DENOM_FUNCTIONS = (
    "instruction",
    "research",
    "public_service",
    "student_services",
    "institutional_support",
)


def build_spend_per_fte(con) -> pd.DataFrame:
    """spend_per_fte — the analysis spine, one row per UNITID × year × function.

    Joins the harmonized finance spine (finance_functions_clean) to hd_clean (for
    stabbr / sector / control / iclevel) and fte_clean (for fte_total), stacks both
    years, and computes:
      - amount_per_fte          = amount_nominal / fte_total
      - amount_per_fte_real2022 = amount_per_fte × (CPI_All_2022 / CPI_All_year)
    Adds an in_both_years flag and a control_matches_hd flag (finance origin vs HD
    control). Null/zero-FTE institutions keep amount_nominal but get NULL per-FTE
    values; the notebook reports the drop count for per-FTE views (design §2/§4/§6).
    """
    sql = f"""
    WITH cpi AS (
        SELECT (SELECT cpi_all_items FROM cpi_clean WHERE year = 2022) AS cpi_2022
    ),
    both_years AS (
        SELECT unitid FROM finance_functions_clean
        GROUP BY unitid HAVING COUNT(DISTINCT year) = 2
    ),
    spine AS (
        SELECT
            f.unitid,
            f.year,
            f.control,                               -- finance-file origin (public/private_np)
            f.function,
            f.source_col,
            f.amount                     AS amount_nominal,
            h.instnm,
            h.stabbr,
            h.sector,
            h.control                    AS hd_control,
            h.iclevel,
            t.fte_total,
            cc.cpi_all_items             AS cpi_year
        FROM finance_functions_clean f
        LEFT JOIN hd_clean  h  ON f.unitid = h.unitid AND f.year = h.year
        LEFT JOIN fte_clean t  ON f.unitid = t.unitid AND f.year = t.year
        LEFT JOIN cpi_clean cc ON f.year = cc.year
    )
    SELECT
        s.unitid,
        s.year,
        s.control,
        s.function,
        s.source_col,
        s.amount_nominal,
        s.instnm,
        s.stabbr,
        s.sector,
        s.hd_control,
        s.iclevel,
        s.fte_total,
        s.cpi_year,
        CASE WHEN s.fte_total IS NULL OR s.fte_total = 0 THEN NULL
             ELSE s.amount_nominal / s.fte_total END AS amount_per_fte,
        CASE WHEN s.fte_total IS NULL OR s.fte_total = 0 THEN NULL
             ELSE (s.amount_nominal / s.fte_total) * (c.cpi_2022 / s.cpi_year)
        END AS amount_per_fte_real2022,
        (b.unitid IS NOT NULL) AS in_both_years,  -- noqa
        -- public finance origin should map to HD control 1; private_np to HD control 2
        ((s.control = 'public'     AND s.hd_control = 1) OR
         (s.control = 'private_np' AND s.hd_control = 2)) AS control_matches_hd
    FROM spine s
    CROSS JOIN cpi c
    LEFT JOIN both_years b ON s.unitid = b.unitid
    ORDER BY s.unitid, s.year, s.function
    """
    return run_sql(sql, con)


def build_chart_admin_vs_instruction_by_sector(con) -> pd.DataFrame:
    """chart_admin_vs_instruction_by_sector — the LEAD chart table.

    control × year × {instruction, institutional_support}: mean per-FTE real-2022-$
    across institutions (per-FTE views drop null/zero-FTE rows). This is the direct
    "admin vs classroom dollars per student, public vs private, 2012 vs 2022" cut.
    """
    sql = """
    SELECT control, year, function,
           COUNT(*) FILTER (WHERE amount_per_fte_real2022 IS NOT NULL) AS n_institutions,
           AVG(amount_per_fte_real2022) AS mean_per_fte_real2022,
           MEDIAN(amount_per_fte_real2022) AS median_per_fte_real2022
    FROM spend_per_fte
    WHERE function IN ('instruction', 'institutional_support')
    GROUP BY control, year, function
    ORDER BY control, function, year
    """
    return run_sql(sql, con)


def build_chart_admin_share_trend(con) -> pd.DataFrame:
    """chart_admin_share_trend — institutional support as a share of functional spending.

    control × year: admin (institutional_support) dollars as a share of the single
    §1.2-note-3 denominator = SUM over {instruction, research, public_service,
    student_services, institutional_support}, built identically per sector from the
    in-pipeline function totals (NEVER a raw IPEDS total line). Computed at the
    institution level then averaged, so each school weighs equally.
    """
    denom_list = ", ".join(f"'{f}'" for f in _SHARE_DENOM_FUNCTIONS)
    sql = f"""
    WITH per_unit AS (
        SELECT unitid, year, control,
               SUM(amount_nominal) FILTER (WHERE function IN ({denom_list})) AS denom,
               SUM(amount_nominal) FILTER (WHERE function = 'institutional_support') AS admin
        FROM spend_per_fte
        GROUP BY unitid, year, control
    )
    SELECT control, year,
           COUNT(*) FILTER (WHERE denom > 0) AS n_institutions,
           AVG(admin / NULLIF(denom, 0)) AS mean_admin_share,
           MEDIAN(admin / NULLIF(denom, 0)) AS median_admin_share
    FROM per_unit
    GROUP BY control, year
    ORDER BY control, year
    """
    return run_sql(sql, con)


def build_chart_spend_by_function_by_year(con) -> pd.DataFrame:
    """chart_spend_by_function_by_year — per-FTE real-$ by function, by sector, by year.

    control × year × function: mean per-FTE real-2022-$ for all six harmonized
    functions. academic_support is carried PER SECTOR (its own control rows); the
    chart that consumes this must never place academic_support in a public-vs-private
    comparison (design §1.2 handling note 1) — but the table itself is per-sector, so
    that constraint is a viz choice, documented here.
    """
    sql = """
    SELECT control, year, function,
           COUNT(*) FILTER (WHERE amount_per_fte_real2022 IS NOT NULL) AS n_institutions,
           AVG(amount_per_fte_real2022) AS mean_per_fte_real2022
    FROM spend_per_fte
    GROUP BY control, year, function
    ORDER BY control, year, function
    """
    return run_sql(sql, con)


def build_chart_admin_per_fte_by_state(con) -> pd.DataFrame:
    """chart_admin_per_fte_by_state — admin-per-FTE by state × sector, with 2012→2022 change.

    stabbr × control: mean institutional-support-per-FTE real-2022-$ in each year,
    plus the absolute and percent change 2012→2022. Only real US state/DC postal
    codes are kept (two-letter, excludes territories/unknown) to keep the state map
    clean; the change columns are NULL where a sector has no institutions in a year.
    """
    sql = """
    WITH admin AS (
        SELECT stabbr, control, year,
               AVG(amount_per_fte_real2022) AS admin_per_fte_real2022,
               COUNT(*) FILTER (WHERE amount_per_fte_real2022 IS NOT NULL) AS n_institutions
        FROM spend_per_fte
        WHERE function = 'institutional_support'
          AND stabbr IS NOT NULL AND LENGTH(stabbr) = 2
        GROUP BY stabbr, control, year
    ),
    by_state AS (
        SELECT stabbr, control,
               MAX(CASE WHEN year = 2012 THEN admin_per_fte_real2022 END) AS admin_2012,
               MAX(CASE WHEN year = 2022 THEN admin_per_fte_real2022 END) AS admin_2022,
               MAX(CASE WHEN year = 2012 THEN n_institutions END) AS n_2012,
               MAX(CASE WHEN year = 2022 THEN n_institutions END) AS n_2022
        FROM admin
        GROUP BY stabbr, control
    )
    SELECT stabbr, control, admin_2012, admin_2022, n_2012, n_2022,
           (admin_2022 - admin_2012) AS admin_change,
           CASE WHEN admin_2012 > 0 THEN (admin_2022 - admin_2012) / admin_2012 END AS admin_pct_change
    FROM by_state
    ORDER BY control, stabbr
    """
    return run_sql(sql, con)


def build_chart_admin_per_fte_by_state_top_bottom(con) -> pd.DataFrame:
    """chart_admin_per_fte_by_state_top_bottom — the TOP-5 + BOTTOM-5 states per sector.

    The full `chart_admin_per_fte_by_state` cut is ~100+ rows per sector — far too
    many bars to read. For the by-state chart the owner asked for the 5 states where
    admin-per-FTE rose MOST and the 5 where it fell MOST (= top 5 + bottom 5 = 10 bars)
    over the decade, ranked by the 2012→2022 dollar change in institutional-support
    per FTE (`admin_change`), **within each `control` separately** (public and
    private_np each get their own 10).

    States missing a sector in either year have NULL `admin_change` and are excluded.
    If a sector has <= 10 eligible states, all of them pass (still <= 10 bars). A
    `band` column flags 'top' (rising) vs 'bottom' (falling) for readability; rows are
    ordered `control, admin_change` so a diverging-bars render reads bottom→top.
    """
    sql = """
    WITH base AS (
        SELECT stabbr, control, admin_2012, admin_2022, n_2012, n_2022,
               admin_change, admin_pct_change
        FROM chart_admin_per_fte_by_state
        WHERE admin_change IS NOT NULL
    ),
    ranked AS (
        SELECT *,
               ROW_NUMBER() OVER (PARTITION BY control ORDER BY admin_change DESC) AS rank_top,
               ROW_NUMBER() OVER (PARTITION BY control ORDER BY admin_change ASC)  AS rank_bottom
        FROM base
    )
    SELECT stabbr, control, admin_2012, admin_2022, n_2012, n_2022,
           admin_change, admin_pct_change,
           CASE WHEN rank_top <= 5 THEN 'top' ELSE 'bottom' END AS band
    FROM ranked
    WHERE rank_top <= 5 OR rank_bottom <= 5
    ORDER BY control, admin_change
    """
    return run_sql(sql, con)


def build_chart_tuition_vs_cpi(con) -> pd.DataFrame:
    """chart_tuition_vs_cpi — sticker tuition vs CPI-U All-Items vs CPI tuition subindex.

    Returns the full CPI-U series (All-Items + college-tuition subindex, both indexed
    to 2012 = 100 for a clean "how fast did each rise" comparison) plus the national
    mean in-state (public) / out-of-state and private sticker tuition for BOTH 2012
    and 2022 — carried BOTH as nominal (as-reported) dollars AND as constant-2022
    dollars.

    ✅ Constant-2022-dollar basis (consistency with the finance tables). Every OTHER
    chart in this project is in constant 2022 dollars (the per-FTE finance tables are
    `*_per_fte_real2022`, deflated via CPI-U All-Items). The tuition series must match
    so a 2012→2022 tuition comparison does not mix nominal-vs-real. Each year's nominal
    mean is deflated to 2022 dollars with the SAME CPI-U All-Items deflator used for
    the finance spine:
        real2022 = nominal × (CPI_All_2022 / CPI_All_year)
    so 2012 nominal is scaled up by CPI_2022/CPI_2012 = 292.655/229.594 = 1.27466 and
    2022 values are unchanged (deflator 1.0, since 2022 is the base year). The deflator
    is read live from `cpi_clean` (not hardcoded). The charted/trend value is the
    `*_real2022` column; the `*_nominal` columns are kept for provenance.

    ✅ 2012 sticker tuition is now REAL. The IPEDS IC2012_AY file had originally been
    ingested malformed (every unitid/tuition value read as the literal string "R");
    that was repaired upstream at 01-ingest (an index_col=False fix in the IPEDS
    reader), and 02-clean re-ran so charges_clean now carries real non-null 2012
    tuition (4,455 institutions, matching the ~4,455/4,806 2012 reporting rate).
    This table therefore carries CPI All-Items + the tuition subindex for the full
    2012–2022 window AND real sticker-tuition dollars (nominal + constant-2022) for
    BOTH years, so a tuition-dollars-over-time comparison can now be drawn directly
    on the same constant-2022-$ basis as the finance charts.
    """
    sql = """
    WITH tuition AS (
        SELECT c.year,
               AVG(c.tuition_in_state)  FILTER (WHERE h.control = 1) AS mean_tuition_public_in_state,
               AVG(c.tuition_out_state) FILTER (WHERE h.control = 1) AS mean_tuition_public_out_state,
               AVG(c.tuition_in_state)  FILTER (WHERE h.control = 2) AS mean_tuition_private,
               COUNT(c.tuition_in_state) AS n_tuition_reported
        FROM charges_clean c
        LEFT JOIN hd_clean h
               ON TRY_CAST(c.unitid AS BIGINT) = h.unitid AND c.year = h.year
        GROUP BY c.year
    ),
    base AS (
        SELECT cpi_all_items AS cpi_all_2012, cpi_tuition_subindex AS cpi_tuition_2012
        FROM cpi_clean WHERE year = 2012
    ),
    cpi2022 AS (
        SELECT cpi_all_items AS cpi_all_2022 FROM cpi_clean WHERE year = 2022
    )
    SELECT cpi.year,
           cpi.cpi_all_items,
           cpi.cpi_tuition_subindex,
           100.0 * cpi.cpi_all_items       / b.cpi_all_2012     AS cpi_all_index_2012base,
           100.0 * cpi.cpi_tuition_subindex / b.cpi_tuition_2012 AS cpi_tuition_index_2012base,
           -- The CPI-U All-Items deflator applied to this year's nominal tuition to
           -- restate it in constant 2022 dollars (1.0 for 2022, the base year).
           (c22.cpi_all_2022 / cpi.cpi_all_items)               AS cpi_all_deflator_to_2022,
           -- Nominal (as-reported) sticker tuition means.
           t.mean_tuition_public_in_state   AS mean_tuition_public_in_state_nominal,
           t.mean_tuition_public_out_state  AS mean_tuition_public_out_state_nominal,
           t.mean_tuition_private           AS mean_tuition_private_nominal,
           -- Constant-2022-dollar sticker tuition means (CPI-U All-Items deflated) —
           -- the charted/trend values, consistent with the per-FTE finance tables.
           t.mean_tuition_public_in_state  * (c22.cpi_all_2022 / cpi.cpi_all_items) AS mean_tuition_public_in_state_real2022,
           t.mean_tuition_public_out_state * (c22.cpi_all_2022 / cpi.cpi_all_items) AS mean_tuition_public_out_state_real2022,
           t.mean_tuition_private          * (c22.cpi_all_2022 / cpi.cpi_all_items) AS mean_tuition_private_real2022,
           t.n_tuition_reported
    FROM cpi_clean cpi
    CROSS JOIN base b
    CROSS JOIN cpi2022 c22
    LEFT JOIN tuition t ON cpi.year = t.year
    WHERE cpi.year BETWEEN 2012 AND 2022
    ORDER BY cpi.year
    """
    return run_sql(sql, con)


# ---------------------------------------------------------------------------
# REFRAME — "big education" relative-inflation chart-ready tables
# ---------------------------------------------------------------------------
#
# Suspicion 1 of SECTOR-COMPARISON-INVESTIGATION: has the cost of higher
# education outpaced general inflation and the other "big" sectors? These two
# builders turn the interim cpi_sectors_clean (CPI-U sector subindices, annual
# averages, 1979-2025) into the chart-ready tables the reframed 04-viz consumes.
# 03 OWNS this shaping; 04 only reads it.

# The reframe window floor: the college-tuition subindex begins Dec 1978, so
# 1979 is the common base year every sector is re-indexed to 100 at.
CPI_BASE_YEAR = 1979

# Hospital services (CUUR0000SEMD) begins Dec 1996 — kept in the data but EXCLUDED
# from the 1979-base headline chart (it cannot anchor the common window). Charts
# that use the common 1979 base filter it out; it remains available for a
# late-window detail panel if ever wanted.
CPI_HEADLINE_EXCLUDE = ("Hospital services",)


def build_chart_cpi_indexed(con) -> pd.DataFrame:
    """chart_cpi_indexed — every CPI sector re-indexed to 100 at the 1979 base.

    One row per (sector × year): the sector's annual-average index value divided
    by its OWN value in the base year 1979, ×100. So every sector starts at
    exactly 100.0 in 1979 and the line's height in any later year is the
    cumulative price change since 1979 (e.g. 400 = prices quadrupled). This is
    the classic "which line is steepest" multi-sector inflation chart; college
    tuition is reliably the steepest.

    Columns:
        sector     — human sector name (All items, College tuition & fees, …)
        series_id  — the BLS CUUR series ID (provenance)
        year       — calendar year (1979 … latest full year)
        value      — raw CPI-U annual-average index (published 1982-84=100 base)
        value_1979 — the sector's own 1979 annual-average value (the re-base divisor)
        index_1979base — value / value_1979 × 100 (the charted value; 100.0 in 1979)
        in_headline    — TRUE for the 8 sectors on the 1979 common window; FALSE for
                         hospital services (starts 1996, excluded from the headline)

    All sectors are kept (incl. hospital services) so a consumer can choose; the
    reframed headline chart filters to in_headline = TRUE.
    """
    exclude_sql = ", ".join(f"'{s}'" for s in CPI_HEADLINE_EXCLUDE)
    sql = f"""
    WITH base AS (
        SELECT series_id, value AS value_1979
        FROM cpi_sectors_clean
        WHERE year = {CPI_BASE_YEAR}
    )
    SELECT s.sector,
           s.series_id,
           s.year,
           s.value,
           b.value_1979,
           100.0 * s.value / b.value_1979 AS index_1979base,
           (s.sector NOT IN ({exclude_sql})) AS in_headline
    FROM cpi_sectors_clean s
    JOIN base b USING (series_id)
    WHERE s.year >= {CPI_BASE_YEAR}
    ORDER BY s.sector, s.year
    """
    return run_sql(sql, con)


def build_chart_cpi_pct_change(con) -> pd.DataFrame:
    """chart_cpi_pct_change — total % price change per sector since 1979 (ranked).

    One row per sector: the cumulative percent change in the CPI-U annual-average
    index from the 1979 base year to the latest full year available, i.e.
    (value_latest / value_1979 − 1) × 100. This is the one-number / ranked-bar
    version of the indexed line chart (tuition on top).

    Columns:
        sector      — human sector name
        series_id   — BLS CUUR series ID (provenance)
        base_year   — 1979 (the common base)
        latest_year — latest full year in the data (e.g. 2024/2025)
        value_1979  — annual-average index in 1979
        value_latest— annual-average index in the latest year
        pct_change_since_1979 — (value_latest / value_1979 − 1) × 100, the ranked value
        pct_label   — pre-formatted "+NNN%" string for the bar label
        in_headline — TRUE for the 8 common-window sectors; FALSE for hospital services

    Ordered by pct_change_since_1979 descending (tuition first).
    """
    exclude_sql = ", ".join(f"'{s}'" for s in CPI_HEADLINE_EXCLUDE)
    sql = f"""
    WITH base AS (
        SELECT series_id, value AS value_1979
        FROM cpi_sectors_clean WHERE year = {CPI_BASE_YEAR}
    ),
    latest AS (
        SELECT series_id, MAX(year) AS latest_year
        FROM cpi_sectors_clean GROUP BY series_id
    ),
    latest_val AS (
        SELECT s.series_id, s.year AS latest_year, s.value AS value_latest
        FROM cpi_sectors_clean s JOIN latest l
          ON s.series_id = l.series_id AND s.year = l.latest_year
    )
    SELECT c.sector,
           c.series_id,
           {CPI_BASE_YEAR} AS base_year,
           lv.latest_year,
           b.value_1979,
           lv.value_latest,
           100.0 * (lv.value_latest / b.value_1979 - 1.0) AS pct_change_since_1979,
           ('+' || CAST(ROUND(100.0 * (lv.value_latest / b.value_1979 - 1.0)) AS INTEGER) || '%')
               AS pct_label,
           (c.sector NOT IN ({exclude_sql})) AS in_headline
    FROM (SELECT DISTINCT sector, series_id FROM cpi_sectors_clean) c
    JOIN base b      USING (series_id)
    JOIN latest_val lv USING (series_id)
    ORDER BY pct_change_since_1979 DESC
    """
    return run_sql(sql, con)


def build_chart_cpi_vs_allitems(con) -> pd.DataFrame:
    """chart_cpi_vs_allitems — each sector's price change RELATIVE TO All Items.

    The "above/below general inflation" reframe of the %-change bar (option "b").
    Where chart_cpi_pct_change measures each sector's TOTAL % change since 1979,
    this measures how much each sector OUT-RAN (or lagged) general inflation over
    the SAME window:

        pct_vs_allitems = (sector_index_latest / allitems_index_latest - 1) * 100

    equivalently ((100 + sector_pct) / (100 + allitems_pct) - 1) * 100. So All
    Items sits at exactly 0 (it is the reference/zero point), sectors that beat
    general inflation are positive, and sectors that lagged it are negative. This
    is the diverging-bar table: college tuition is the largest positive bar;
    energy/gasoline land near or below zero.

    One row per sector (headline sectors only — the 1979 common window; hospital
    services is excluded, same as chart_cpi_pct_change). All Items is kept as a
    row (value 0.0) so the chart can show it as the labeled reference baseline in
    its own distinct color.

    Columns:
        sector      — human sector name
        series_id   — BLS CUUR series ID (provenance)
        base_year   — 1979 (the common base)
        latest_year — latest full year in the data
        index_latest        — the sector's own 1979-based index at the latest year
        allitems_index_latest — All Items' 1979-based index at the latest year (the divisor)
        pct_vs_allitems — (index_latest / allitems_index_latest - 1) * 100; the diverging value
        pct_vs_allitems_label — pre-formatted "+NNN%"/"-NN%" string for the bar
        is_allitems — TRUE for the All Items reference row (value 0.0)
        in_headline — TRUE for the 8 common-window sectors

    Ordered by pct_vs_allitems descending (tuition first, laggards at the bottom).
    """
    exclude_sql = ", ".join(f"'{s}'" for s in CPI_HEADLINE_EXCLUDE)
    sql = f"""
    WITH base AS (
        SELECT series_id, value AS value_1979
        FROM cpi_sectors_clean WHERE year = {CPI_BASE_YEAR}
    ),
    latest AS (
        SELECT series_id, MAX(year) AS latest_year
        FROM cpi_sectors_clean GROUP BY series_id
    ),
    latest_val AS (
        SELECT s.sector, s.series_id, s.year AS latest_year, s.value AS value_latest
        FROM cpi_sectors_clean s JOIN latest l
          ON s.series_id = l.series_id AND s.year = l.latest_year
    ),
    indexed AS (
        SELECT lv.sector, lv.series_id, lv.latest_year,
               100.0 * lv.value_latest / b.value_1979 AS index_latest
        FROM latest_val lv JOIN base b USING (series_id)
    ),
    allitems AS (
        SELECT index_latest AS allitems_index_latest, latest_year
        FROM indexed WHERE sector = 'All items'
    )
    SELECT i.sector,
           i.series_id,
           {CPI_BASE_YEAR} AS base_year,
           i.latest_year,
           i.index_latest,
           a.allitems_index_latest,
           100.0 * (i.index_latest / a.allitems_index_latest - 1.0) AS pct_vs_allitems,
           (CASE WHEN (i.index_latest / a.allitems_index_latest - 1.0) >= 0 THEN '+' ELSE '' END
             || CAST(ROUND(100.0 * (i.index_latest / a.allitems_index_latest - 1.0)) AS INTEGER)
             || '%') AS pct_vs_allitems_label,
           (i.sector = 'All items') AS is_allitems,
           (i.sector NOT IN ({exclude_sql})) AS in_headline
    FROM indexed i
    CROSS JOIN allitems a
    WHERE i.sector NOT IN ({exclude_sql})
    ORDER BY pct_vs_allitems DESC
    """
    return run_sql(sql, con)


def value_counts_all(df: pd.DataFrame, top_n: int = 10) -> None:
    """Print top-N value counts for every column — quick sanity check."""
    for col in df.columns:
        print(f"\n── {col} ──")
        print(df[col].value_counts(dropna=False).head(top_n).to_string())


def numeric_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return describe() output for numeric columns only, transposed for readability."""
    return df.select_dtypes("number").describe().T.round(2)
