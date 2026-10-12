"""DuckDB-backed cleaning and data quality utilities.

Workflow:
  1. Load raw DataFrame into DuckDB (in the project .duckdb file).
  2. Run cleaning operations as SQL — fast, inspectable, reproducible.
  3. Run quality checks and print a report before writing interim output.
  4. Save cleaned table as Parquet to data/interim/.

All functions accept and return pandas DataFrames so notebooks stay readable,
but the heavy lifting happens inside DuckDB.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


# ---------------------------------------------------------------------------
# Source provenance (_sources metadata table)
# ---------------------------------------------------------------------------

_SOURCES_SCHEMA = """
CREATE TABLE IF NOT EXISTS _sources (
    duckdb_table  VARCHAR,
    source_name   VARCHAR,
    url           VARCHAR,
    license       VARCHAR,
    notes         VARCHAR,
    retrieved     VARCHAR,
    methodology   VARCHAR,
    series_breaks VARCHAR
)
"""

# Columns that older databases may be missing (added after the original schema).
_SOURCES_ADDED_COLUMNS = ("methodology", "series_breaks")


def _ensure_sources_columns(con: duckdb.DuckDBPyConnection) -> None:
    """Add later-added _sources columns to pre-existing databases (idempotent)."""
    existing = {row[1] for row in con.execute("PRAGMA table_info('_sources')").fetchall()}
    for col in _SOURCES_ADDED_COLUMNS:
        if col not in existing:
            con.execute(f"ALTER TABLE _sources ADD COLUMN {col} VARCHAR")


def register_source(
    con: duckdb.DuckDBPyConnection,
    table: str,
    name: str,
    url: str = "",
    license: str = "",
    notes: str = "",
    retrieved: str = "",
    methodology: str = "",
    series_breaks: str = "",
) -> None:
    """Register a data source in the _sources metadata table.

    Call this after loading a new table into DuckDB to maintain full provenance.
    Replaces any existing entry for the same table name.

    Args:
        con:           Open DuckDB connection.
        table:         DuckDB table name this source populates.
        name:          Human-readable source name (e.g., "NHTSA FARS 2024").
        url:           Direct URL to the data file or page.
        license:       License string (e.g., "Public domain", "CC-BY 4.0").
        notes:         Any caveats or field descriptions.
        retrieved:     Date retrieved as ISO string (YYYY-MM-DD). Defaults to today.
        methodology:   How the source collects and defines the data.
        series_breaks: Dates/boundaries across which the numbers are NOT comparable.
    """
    from datetime import date as _date

    if not retrieved:
        retrieved = _date.today().isoformat()

    con.execute(_SOURCES_SCHEMA)
    _ensure_sources_columns(con)
    con.execute("DELETE FROM _sources WHERE duckdb_table = ?", [table])
    con.execute(
        """INSERT INTO _sources
           (duckdb_table, source_name, url, license, notes, retrieved,
            methodology, series_breaks)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [table, name, url, license, notes, retrieved, methodology, series_breaks],
    )


def get_sources(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return the full _sources provenance table as a DataFrame."""
    con.execute(_SOURCES_SCHEMA)
    return con.execute("SELECT * FROM _sources ORDER BY duckdb_table").df()


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def get_connection(cfg: dict[str, Any]) -> duckdb.DuckDBPyConnection:
    """Open (or create) the project DuckDB file and return a connection."""
    db_path = Path(cfg["settings"]["duckdb_file"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def load_to_duckdb(
    df: pd.DataFrame,
    table_name: str,
    con: duckdb.DuckDBPyConnection,
    replace: bool = True,
) -> None:
    """Register a DataFrame as a DuckDB table.

    Args:
        df:         Source DataFrame.
        table_name: Name for the table inside DuckDB.
        con:        Open DuckDB connection.
        replace:    Drop and recreate if the table already exists.
    """
    if replace:
        con.execute(f"DROP TABLE IF EXISTS {table_name}")
    # DuckDB can read a pandas DataFrame directly via the local variable name
    con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")


# ---------------------------------------------------------------------------
# Cleaning operations
# ---------------------------------------------------------------------------

def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase column names and replace spaces/hyphens with underscores."""
    df.columns = [
        c.strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns
    ]
    return df


def clean_table(
    df: pd.DataFrame,
    table_name: str,
    con: duckdb.DuckDBPyConnection,
    drop_duplicate_subset: list[str] | None = None,
    strip_columns: list[str] | None = None,
    cast_map: dict[str, str] | None = None,
    where_filter: str | None = None,
) -> pd.DataFrame:
    """Run a cleaning pass on a DataFrame inside DuckDB and return the result.

    Args:
        df:                    Raw DataFrame to clean.
        table_name:            Staging table name in DuckDB.
        con:                   Open DuckDB connection.
        drop_duplicate_subset: Column(s) to use for deduplication (None = all cols).
        strip_columns:         String columns to TRIM whitespace from.
        cast_map:              Dict of {column: duckdb_type} to cast, e.g. {"year": "INTEGER"}.
        where_filter:          Optional SQL WHERE clause (no 'WHERE' keyword) to filter rows.

    Returns:
        Cleaned DataFrame.
    """
    load_to_duckdb(df, table_name, con)

    # Build SELECT list with optional casts and trims
    col_exprs = []
    for col in df.columns:
        expr = f'"{col}"'
        if cast_map and col in cast_map:
            expr = f"TRY_CAST({expr} AS {cast_map[col]}) AS \"{col}\""
        elif strip_columns and col in strip_columns:
            expr = f"TRIM({expr}) AS \"{col}\""
        else:
            expr = f"{expr}"
        col_exprs.append(expr)

    select_clause = ", ".join(col_exprs)
    query = f"SELECT {select_clause} FROM {table_name}"
    if where_filter:
        query += f" WHERE {where_filter}"

    cleaned = con.execute(query).df()

    # Deduplication via pandas (easier to express cross-DB)
    if drop_duplicate_subset is not None:
        cleaned = cleaned.drop_duplicates(subset=drop_duplicate_subset)
    else:
        cleaned = cleaned.drop_duplicates()

    return cleaned.reset_index(drop=True)


def run_sql(sql: str, con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Run arbitrary SQL against the open DuckDB connection and return a DataFrame.

    Useful for custom joins, aggregations, and feature engineering in notebooks.

    Example:
        run_sql("SELECT state, AVG(rate) as avg_rate FROM cleaned GROUP BY state", con)
    """
    return con.execute(sql).df()


# ---------------------------------------------------------------------------
# Quality checks
# ---------------------------------------------------------------------------

def quality_report(
    df: pd.DataFrame,
    table_name: str,
    con: duckdb.DuckDBPyConnection,
    required_columns: list[str] | None = None,
    max_null_pct: float = 0.10,
) -> dict[str, Any]:
    """Run quality checks and print a summary report.

    Checks:
      - Row count
      - Null percentage per column (warns if above max_null_pct)
      - Duplicate row count
      - Presence of required columns

    Returns a dict with check results (useful for notebook assertions).
    """
    load_to_duckdb(df, f"_qc_{table_name}", con, replace=True)

    row_count = con.execute(f"SELECT COUNT(*) FROM _qc_{table_name}").fetchone()[0]
    dup_count = row_count - con.execute(
        f"SELECT COUNT(*) FROM (SELECT DISTINCT * FROM _qc_{table_name})"
    ).fetchone()[0]

    null_pcts: dict[str, float] = {}
    warnings: list[str] = []
    for col in df.columns:
        nulls = con.execute(
            f'SELECT COUNT(*) FROM _qc_{table_name} WHERE "{col}" IS NULL'
        ).fetchone()[0]
        pct = nulls / row_count if row_count else 0.0
        null_pcts[col] = round(pct, 4)
        if pct > max_null_pct:
            warnings.append(f"  ⚠  '{col}' is {pct:.1%} null (threshold {max_null_pct:.0%})")

    missing_cols: list[str] = []
    if required_columns:
        missing_cols = [c for c in required_columns if c not in df.columns]
        if missing_cols:
            warnings.append(f"  ✗  Missing required columns: {missing_cols}")

    print(f"\n── Quality report: {table_name} ──────────────────")
    print(f"  Rows       : {row_count:,}")
    print(f"  Duplicates : {dup_count:,}")
    print(f"  Null %     :")
    for col, pct in null_pcts.items():
        flag = " ⚠" if pct > max_null_pct else ""
        print(f"    {col:<30} {pct:.1%}{flag}")
    if warnings:
        print("\n  Warnings:")
        for w in warnings:
            print(w)
    else:
        print("\n  ✓  No issues found.")
    print("─" * 50)

    return {
        "row_count": row_count,
        "duplicate_count": dup_count,
        "null_pcts": null_pcts,
        "missing_required_columns": missing_cols,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------

def save_interim(df: pd.DataFrame, cfg: dict[str, Any], filename: str) -> Path:
    """Save a cleaned DataFrame to data/interim/ as Parquet."""
    out = Path(cfg["paths"]["data_interim"]) / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False, engine=cfg["settings"]["parquet_engine"])
    print(f"Saved interim → {out}  ({len(df):,} rows)")
    return out


def save_processed(df: pd.DataFrame, cfg: dict[str, Any], filename: str) -> Path:
    """Save an analysis-ready DataFrame to data/processed/ as Parquet."""
    out = Path(cfg["paths"]["data_processed"]) / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False, engine=cfg["settings"]["parquet_engine"])
    print(f"Saved processed → {out}  ({len(df):,} rows)")
    return out


# ===========================================================================
# Project-specific harmonization helpers — higher-education-cost (02-clean)
# ===========================================================================
#
# Everything below is DuckDB-SQL based (no pandas chained transforms). They
# turn the 12 _raw tables (+ re-ingested EFIA FTE + re-pulled CPI) into the
# harmonized, quality-checked interim `_clean` tables described in
# artifacts/HARMONIZATION-DESIGN.md §8.1.
#
# ⭐ GASB/FASB function crosswalk — DICTIONARY-CONFIRMED (design §1.2 "the
# dictionary wins"). The IPEDS F1A/F2 data dictionaries (2012 & 2022) were read
# directly (varlist sheet). The design draft mapped GASB to F1E01–F1E07, which
# the dictionary shows are the SCHOLARSHIPS/GRANTS block, NOT expenses by
# function. The real GASB expenses-by-function block is **F1C**, and its
# function index differs from FASB's. The confirmed mapping:
#
#   function                 GASB (F1C)   FASB (F2E)   dict varTitle (both agree)
#   instruction              F1C011       F2E011       "Instruction"
#   research                 F1C021       F2E021       "Research"
#   public_service           F1C031       F2E031       "Public service"
#   academic_support         F1C051       F2E041       "Academic support"
#   student_services         F1C061       F2E051       "Student service(s)"
#   institutional_support    F1C071       F2E061       "Institutional support"  (= admin)
#   total_expenses           F1C191       F2E131       "Total expenses ..."     (sidecar only)
#
# The five charted/comparable-core functions are instruction, research,
# student_services, institutional_support, plus academic_support. (The design
# flagged academic_support as GASB-sparse, but that was based on the WRONG
# column F1E04; the correct F1C051 is well-populated in both sectors — the
# per-sector coverage printed by quality_report() documents this.)

# Harmonized function  ->  (GASB F1C total column, FASB F2E total column)
FUNCTION_CROSSWALK: dict[str, tuple[str, str]] = {
    "instruction":           ("F1C011", "F2E011"),
    "research":              ("F1C021", "F2E021"),
    "public_service":        ("F1C031", "F2E031"),
    "academic_support":      ("F1C051", "F2E041"),
    "student_services":      ("F1C061", "F2E051"),
    "institutional_support": ("F1C071", "F2E061"),
}
# Per-standard grand-total columns (sidecar reconciliation only — never charted,
# never a share denominator). GASB F1C191 / FASB F2E131 (NOT F2E071).
FINANCE_TOTAL_COLS: dict[str, str] = {"gasb": "F1C191", "fasb": "F2E131"}


def confirm_finance_dictionary(
    con: duckdb.DuckDBPyConnection,
    dict_zip_paths: dict[str, Path],
) -> pd.DataFrame:
    """§1.2 hard precondition — dictionary-confirm every used finance function code.

    Reads the IPEDS F1A/F2 data-dictionary ``varlist`` sheet (shipped as an .xlsx
    inside each ``<FILE>_Dict.zip``) and returns the official ``varTitle`` for every
    GASB F1C / FASB F2E code the crosswalk uses, for whichever years are supplied.
    The caller asserts the titles agree with FUNCTION_CROSSWALK before building the
    finance spine; if they disagree the dictionary wins and the crosswalk is fixed.

    Args:
        con:            Open DuckDB connection (unused for reads here; kept for a
                        uniform helper signature / future table-backed checks).
        dict_zip_paths: Map of a label (e.g. "gasb_2022") -> Path to that survey's
                        ``_Dict.zip``.

    Returns:
        Long DataFrame: label, standard, year, varname, varTitle — one row per
        confirmed code per supplied dictionary.
    """
    import io
    import zipfile

    gasb_codes = {g for g, _ in FUNCTION_CROSSWALK.values()} | {FINANCE_TOTAL_COLS["gasb"]}
    fasb_codes = {f for _, f in FUNCTION_CROSSWALK.values()} | {FINANCE_TOTAL_COLS["fasb"]}

    rows: list[dict[str, Any]] = []
    for label, zp in dict_zip_paths.items():
        standard = "gasb" if "gasb" in label else "fasb"
        year = "".join(ch for ch in label if ch.isdigit())
        wanted = gasb_codes if standard == "gasb" else fasb_codes
        with zipfile.ZipFile(zp) as zf:
            xlsx = [n for n in zf.namelist() if n.lower().endswith(".xlsx")][0]
            vl = pd.ExcelFile(io.BytesIO(zf.read(xlsx))).parse("varlist")
        for _, r in vl.iterrows():
            vn = str(r["varname"]).strip().upper()
            if vn in wanted:
                rows.append(
                    {
                        "label": label,
                        "standard": standard,
                        "year": year,
                        "varname": vn,
                        "varTitle": str(r["varTitle"]).strip(),
                    }
                )
    return pd.DataFrame(rows).sort_values(["label", "varname"]).reset_index(drop=True)


def assert_finance_columns_present(con: duckdb.DuckDBPyConnection) -> None:
    """Assert every used finance function + total column exists in all four finance tables.

    Raises AssertionError naming any missing code (design §1.2 note 4 / §10).
    """
    gasb_codes = [g for g, _ in FUNCTION_CROSSWALK.values()] + [FINANCE_TOTAL_COLS["gasb"]]
    fasb_codes = [f for _, f in FUNCTION_CROSSWALK.values()] + [FINANCE_TOTAL_COLS["fasb"]]
    checks = {
        "ipeds_finance_gasb_2012_raw": gasb_codes,
        "ipeds_finance_gasb_2022_raw": gasb_codes,
        "ipeds_finance_fasb_2012_raw": fasb_codes,
        "ipeds_finance_fasb_2022_raw": fasb_codes,
    }
    for table, codes in checks.items():
        have = {c.upper() for c in con.execute(f"SELECT * FROM {table} LIMIT 0").df().columns}
        missing = [c for c in codes if c not in have]
        assert not missing, f"{table} missing finance columns: {missing}"


def build_hd_clean(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """hd_clean — institution directory, one row per UNITID × year (stacked 2012+2022)."""
    sql = """
    WITH stacked AS (
        SELECT UNITID AS unitid, 2012 AS year, INSTNM AS instnm, STABBR AS stabbr,
               SECTOR AS sector, CONTROL AS control, ICLEVEL AS iclevel
        FROM ipeds_hd_2012_raw
        UNION ALL
        SELECT UNITID, 2022, INSTNM, STABBR, SECTOR, CONTROL, ICLEVEL
        FROM ipeds_hd_2022_raw
    )
    SELECT unitid, year, TRIM(instnm) AS instnm, TRIM(stabbr) AS stabbr,
           TRY_CAST(sector AS INTEGER) AS sector,
           TRY_CAST(control AS INTEGER) AS control,
           TRY_CAST(iclevel AS INTEGER) AS iclevel
    FROM stacked
    """
    return run_sql(sql, con)


def _finance_melt_sql(standard: str, table: str, year: int, control_label: str) -> str:
    """Return a UNION-ALL SELECT that melts one finance table into the long function schema.

    Reads ONLY the numeric F1C*/F2E* function totals (never an X* imputation flag).
    """
    idx = 0 if standard == "gasb" else 1
    parts = []
    for function, cols in FUNCTION_CROSSWALK.items():
        col = cols[idx]
        parts.append(
            f"SELECT UNITID AS unitid, {year} AS year, '{control_label}' AS control, "
            f"'{function}' AS function, TRY_CAST({col} AS DOUBLE) AS amount, "
            f"'{col}' AS source_col FROM {table}"
        )
    return "\nUNION ALL\n".join(parts)


def build_finance_functions_clean(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """finance_functions_clean — the harmonized long spine.

    One row per UNITID × year × function, each tagged control (public = GASB rows,
    private_np = FASB rows) with nominal `amount` and the `source_col` it came from.
    Built from the dictionary-confirmed F1C (GASB) / F2E (FASB) crosswalk, all in
    DuckDB SQL (design §1.2 / §8.1).
    """
    blocks = [
        _finance_melt_sql("gasb", "ipeds_finance_gasb_2012_raw", 2012, "public"),
        _finance_melt_sql("gasb", "ipeds_finance_gasb_2022_raw", 2022, "public"),
        _finance_melt_sql("fasb", "ipeds_finance_fasb_2012_raw", 2012, "private_np"),
        _finance_melt_sql("fasb", "ipeds_finance_fasb_2022_raw", 2022, "private_np"),
    ]
    sql = "\nUNION ALL\n".join(blocks)
    return run_sql(sql, con)


def build_finance_totals_clean(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """finance_totals_clean — sidecar per-standard grand totals for §10 reconciliation only.

    One row per UNITID × year × control with `raw_total` = GASB F1C191 / FASB F2E131.
    Never charted, never a share denominator (design §1.2 note 3).
    """
    g_tot = FINANCE_TOTAL_COLS["gasb"]
    f_tot = FINANCE_TOTAL_COLS["fasb"]
    sql = f"""
    SELECT UNITID AS unitid, 2012 AS year, 'public' AS control,
           TRY_CAST({g_tot} AS DOUBLE) AS raw_total FROM ipeds_finance_gasb_2012_raw
    UNION ALL
    SELECT UNITID, 2022, 'public', TRY_CAST({g_tot} AS DOUBLE) FROM ipeds_finance_gasb_2022_raw
    UNION ALL
    SELECT UNITID, 2012, 'private_np', TRY_CAST({f_tot} AS DOUBLE) FROM ipeds_finance_fasb_2012_raw
    UNION ALL
    SELECT UNITID, 2022, 'private_np', TRY_CAST({f_tot} AS DOUBLE) FROM ipeds_finance_fasb_2022_raw
    """
    return run_sql(sql, con)


def build_fte_clean(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """fte_clean — one row per UNITID × year: fte_total from the re-ingested EFIA file.

    fte_total = reported undergrad FTE (FTEUG) + reported grad FTE (FTEGD), each
    coalesced to 0 (FTEGD is null for institutions with no graduate programs).
    EFIA is the authoritative IPEDS 12-month FTE (design §4) — one row per UNITID.
    Requires ipeds_fte_2012_raw / ipeds_fte_2022_raw (blocker B1).
    """
    sql = """
    SELECT UNITID AS unitid, 2012 AS year,
           COALESCE(TRY_CAST(FTEUG AS DOUBLE), 0) + COALESCE(TRY_CAST(FTEGD AS DOUBLE), 0) AS fte_total
    FROM ipeds_fte_2012_raw
    UNION ALL
    SELECT UNITID, 2022,
           COALESCE(TRY_CAST(FTEUG AS DOUBLE), 0) + COALESCE(TRY_CAST(FTEGD AS DOUBLE), 0)
    FROM ipeds_fte_2022_raw
    """
    return run_sql(sql, con)


def build_charges_clean(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """charges_clean — sticker price, one row per UNITID × year, three residency tiers.

    IC_AY dictionary-confirmed mapping (design §7): TUITION1 = in-district,
    TUITION2 = in-state, TUITION3 = out-of-state, with matching FEE1/2/3.
    Sticker price only — kept DISTINCT from Scorecard net price (§7).
    """
    sql = """
    SELECT UNITID AS unitid, 2012 AS year,
           TRY_CAST(TUITION1 AS DOUBLE) AS tuition_in_district,
           TRY_CAST(FEE1 AS DOUBLE)     AS fee_in_district,
           TRY_CAST(TUITION2 AS DOUBLE) AS tuition_in_state,
           TRY_CAST(FEE2 AS DOUBLE)     AS fee_in_state,
           TRY_CAST(TUITION3 AS DOUBLE) AS tuition_out_state,
           TRY_CAST(FEE3 AS DOUBLE)     AS fee_out_state
    FROM ipeds_charges_2012_raw
    UNION ALL
    SELECT UNITID, 2022,
           TRY_CAST(TUITION1 AS DOUBLE), TRY_CAST(FEE1 AS DOUBLE),
           TRY_CAST(TUITION2 AS DOUBLE), TRY_CAST(FEE2 AS DOUBLE),
           TRY_CAST(TUITION3 AS DOUBLE), TRY_CAST(FEE3 AS DOUBLE)
    FROM ipeds_charges_2022_raw
    """
    return run_sql(sql, con)


def build_net_price_clean(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """net_price_clean — Scorecard net price, one row per UNITID (snapshot, no year).

    net_price_pub (NPT4_PUB) / net_price_priv (NPT4_PRIV) / cost_attendance (COSTT4_A).
    Net price != sticker price — kept in a separate table (design §7).
    """
    sql = """
    SELECT TRY_CAST(UNITID AS BIGINT) AS unitid,
           TRY_CAST(NPT4_PUB AS DOUBLE)  AS net_price_pub,
           TRY_CAST(NPT4_PRIV AS DOUBLE) AS net_price_priv,
           TRY_CAST(COSTT4_A AS DOUBLE)  AS cost_attendance
    FROM scorecard_raw
    """
    return run_sql(sql, con)


def build_cpi_clean(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """cpi_clean — one row per year: cpi_all_items + cpi_tuition_subindex, M13 annual avg.

    year/value are VARCHAR in cpi_u_raw → TRY_CAST before any filter (design §5).
    All-Items = CUUR0000SA0 (deflator); tuition subindex = CUUR0000SEEB01 (comparison
    only, never a deflator). Requires cpi_u_raw to reach ≥2022 (blocker B2).
    """
    sql = """
    SELECT TRY_CAST(year AS INTEGER) AS year,
           MAX(CASE WHEN series_id = 'CUUR0000SA0'    THEN TRY_CAST(value AS DOUBLE) END) AS cpi_all_items,
           MAX(CASE WHEN series_id = 'CUUR0000SEEB01' THEN TRY_CAST(value AS DOUBLE) END) AS cpi_tuition_subindex
    FROM cpi_u_raw
    WHERE period = 'M13'
    GROUP BY TRY_CAST(year AS INTEGER)
    ORDER BY year
    """
    return run_sql(sql, con)


# ===========================================================================
# REFRAME EXPANSION — cleaning builders for Sources A–D (02-clean)
# ===========================================================================
#
# Four more interim _clean tables, all DuckDB-SQL based:
#   A. tuition_longrun_clean          — tidy long NCES 330.10 (already long in ingest).
#   B. delta_spending_clean /         — Delta per-institution + national spending by
#      delta_spending_national_clean    function, with per-FTE AND SHARES (1987-2012).
#   C. finance_tail_clean /           — raw-IPEDS 2013-2021 harmonized onto Delta's
#      spending_mix_clean               categories; stacked national 1987->latest series.
#   D. hr_staff_clean /               — IPEDS HR admin (Management=STAFFCAT 1300) vs
#      hr_staff_national_clean          faculty (Instructional=1210) headcount + FTE.
#
# ⭐ Honest framing enforced in the SHARE math: the comparable denominator is the
# in-pipeline sum of the SAME core functions used elsewhere (instruction, research,
# public_service, academic_support, student_services, institutional_support), so a
# function's SHARE is "share of core functional spending". The finding the data
# supports is "non-instructional (student services + academic support + institutional
# support) outgrew instruction", NOT "administrators alone exploded" — institutional
# support (admin) alone is roughly flat (see 03/04).

# Delta CFI-method function column -> harmonized function name (same taxonomy as
# the GASB/FASB crosswalk above, so the 1987-2012 Delta series and the 2013+ raw
# tail stack onto identical category labels).
DELTA_FUNCTION_COLS: dict[str, str] = {
    "instruction01": "instruction",
    "research01":    "research",
    "pubserv01":     "public_service",
    "acadsupp01":    "academic_support",
    "studserv01":    "student_services",
    "instsupp01":    "institutional_support",
}
# The core functions summed to form the SHARE denominator (identical everywhere).
SPEND_CORE_FUNCTIONS = (
    "instruction", "research", "public_service",
    "academic_support", "student_services", "institutional_support",
)


def build_tuition_longrun_clean(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """tuition_longrun_clean — tidy long NCES 330.10 (one row per year×control×level×basis×component).

    nces_tuition_longrun_raw is already tidy-long from the ingest parser; this is a
    light typing/validation pass (cast year_start/value/base_year to numeric, trim
    the string dims). All cleaning stays in DuckDB.
    """
    sql = """
    SELECT TRIM(academic_year)        AS academic_year,
           TRY_CAST(year_start AS INTEGER) AS year_start,
           LOWER(TRIM(control))       AS control,
           LOWER(TRIM(level))         AS level,
           LOWER(TRIM(dollar_basis))  AS dollar_basis,
           TRY_CAST(base_year AS INTEGER)  AS base_year,
           LOWER(TRIM(cost_component)) AS cost_component,
           TRY_CAST(value AS DOUBLE)  AS value
    FROM nces_tuition_longrun_raw
    WHERE value IS NOT NULL
    ORDER BY control, level, cost_component, dollar_basis, year_start
    """
    return run_sql(sql, con)


def _delta_melt_sql() -> str:
    """UNION-ALL melt of delta_cost_raw into the long function schema (public+private NP only)."""
    parts = []
    for col, fn in DELTA_FUNCTION_COLS.items():
        parts.append(
            f"SELECT TRY_CAST(unitid AS BIGINT) AS unitid, "
            f"TRY_CAST(academicyear AS INTEGER) AS year, "
            f"CASE control WHEN 1 THEN 'public' WHEN 2 THEN 'private_np' END AS control, "
            f"'{fn}' AS function, "
            f"TRY_CAST({col} AS DOUBLE) AS amount, "
            f"TRY_CAST(fte12mn AS DOUBLE) AS fte_total "
            f"FROM delta_cost_raw WHERE control IN (1, 2)"
        )
    return "\nUNION ALL\n".join(parts)


def build_delta_spending_clean(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """delta_spending_clean — Delta per-institution spending by function, 1987-2012.

    One row per unitid × year × control × function, carrying nominal `amount`,
    the institution's `fte_total` (Delta's constructed 12-month FTE), per-FTE
    (`amount_per_fte`), and the within-institution SHARE of core functional
    spending (`share`, denominator = sum over SPEND_CORE_FUNCTIONS for that
    unit·year). For-profits are already dropped (control IN (1,2)). Rows with
    null/0 FTE keep `amount` but get NULL per-FTE.
    """
    melt = _delta_melt_sql()
    sql = f"""
    WITH long AS ({melt}),
    denom AS (
        SELECT unitid, year, control, SUM(amount) AS core_total
        FROM long GROUP BY unitid, year, control
    )
    SELECT l.unitid, l.year, l.control, l.function, l.amount, l.fte_total,
           CASE WHEN l.fte_total IS NULL OR l.fte_total = 0 THEN NULL
                ELSE l.amount / l.fte_total END AS amount_per_fte,
           CASE WHEN d.core_total IS NULL OR d.core_total = 0 THEN NULL
                ELSE l.amount / d.core_total END AS share
    FROM long l
    JOIN denom d USING (unitid, year, control)
    WHERE l.control IS NOT NULL
    ORDER BY l.unitid, l.year, l.function
    """
    return run_sql(sql, con)


def _national_spending_sql(source_table: str, source_label: str) -> str:
    """National per-year-per-function aggregate (summed-$ / summed-FTE and summed-share).

    Share is computed as summed function $ / summed core $ across all institutions
    (an institution-size-weighted national share) so the 1987-2012 Delta aggregate
    and the 2013+ raw-tail aggregate stack onto one comparable national series.
    """
    core = ", ".join(f"'{f}'" for f in SPEND_CORE_FUNCTIONS)
    return f"""
    WITH tot AS (
        SELECT year, function, SUM(amount) AS amount, SUM(fte_total) AS fte_total
        FROM {source_table}
        WHERE function IN ({core})
        GROUP BY year, function
    ),
    core_by_year AS (
        SELECT year, SUM(amount) AS core_total FROM tot GROUP BY year
    )
    SELECT t.year, t.function,
           t.amount,
           CASE WHEN t.fte_total > 0 THEN t.amount / t.fte_total END AS per_fte,
           CASE WHEN c.core_total > 0 THEN t.amount / c.core_total END AS share,
           '{source_label}' AS source
    FROM tot t JOIN core_by_year c USING (year)
    """


def build_delta_spending_national_clean(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """delta_spending_national_clean — one row per year×function, national, 1987-2012.

    Enrollment-weighted (summed-$ / summed-FTE) per-FTE and national SHARE across
    all public+private-nonprofit institutions. The trend backbone 1987->2012.
    """
    return run_sql(_national_spending_sql("delta_spending_clean", "delta"), con)


def build_finance_tail_clean(
    con: duckdb.DuckDBPyConnection,
    years: list[int],
    crosswalk: dict[str, tuple[str, str]],
) -> pd.DataFrame:
    """finance_tail_clean — raw-IPEDS 2013-2021 finance harmonized onto Delta categories.

    For each supplied year, melt GASB (F1C*) + FASB (F2E*) function totals to the
    shared long schema, tag control (public=GASB, private_np=FASB), join EFIA
    12-month FTE (ipeds_fte_<yr>_raw: FTEUG + FTEGD), and compute per-FTE + the
    within-institution SHARE of core functional spending — the SAME category
    labels and denominator as the Delta series, so the two stack cleanly across
    the 2012 seam.
    """
    core = ", ".join(f"'{f}'" for f in SPEND_CORE_FUNCTIONS)
    year_blocks = []
    for yr in years:
        gasb_tbl = f"ipeds_finance_gasb_{yr}_raw"
        fasb_tbl = f"ipeds_finance_fasb_{yr}_raw"
        fte_tbl = f"ipeds_fte_{yr}_raw"
        melts = []
        for fn, (gcol, fcol) in crosswalk.items():
            melts.append(
                f"SELECT TRY_CAST(UNITID AS BIGINT) AS unitid, {yr} AS year, 'public' AS control, "
                f"'{fn}' AS function, TRY_CAST({gcol} AS DOUBLE) AS amount FROM {gasb_tbl}"
            )
            melts.append(
                f"SELECT TRY_CAST(UNITID AS BIGINT), {yr}, 'private_np', "
                f"'{fn}', TRY_CAST({fcol} AS DOUBLE) FROM {fasb_tbl}"
            )
        melt_sql = "\nUNION ALL\n".join(melts)
        year_blocks.append(
            f"""
        SELECT m.unitid, m.year, m.control, m.function, m.amount,
               (COALESCE(TRY_CAST(e.FTEUG AS DOUBLE),0) + COALESCE(TRY_CAST(e.FTEGD AS DOUBLE),0)) AS fte_total
        FROM ({melt_sql}) m
        LEFT JOIN {fte_tbl} e ON m.unitid = TRY_CAST(e.UNITID AS BIGINT)
        """
        )
    all_years = "\nUNION ALL\n".join(year_blocks)
    sql = f"""
    WITH long AS ({all_years}),
    denom AS (
        SELECT unitid, year, control, SUM(amount) FILTER (WHERE function IN ({core})) AS core_total
        FROM long GROUP BY unitid, year, control
    )
    SELECT l.unitid, l.year, l.control, l.function, l.amount, l.fte_total,
           CASE WHEN l.fte_total IS NULL OR l.fte_total = 0 THEN NULL
                ELSE l.amount / l.fte_total END AS amount_per_fte,
           CASE WHEN d.core_total IS NULL OR d.core_total = 0 THEN NULL
                ELSE l.amount / d.core_total END AS share
    FROM long l
    JOIN denom d USING (unitid, year, control)
    ORDER BY l.year, l.unitid, l.function
    """
    return run_sql(sql, con)


def build_spending_mix_clean(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """spending_mix_clean — the stacked national spending-by-function series, 1987 -> latest.

    Delta national (1987-2012) UNION the raw-tail national (2013-latest), one row per
    year × function with per_fte, share, and a `source` seam flag. This is the table
    03's spending-mix chart consumes.
    """
    tail_national = _national_spending_sql("finance_tail_clean", "ipeds_raw")
    # The raw-tail national block is a CTE (WITH ...) query, so it must be wrapped
    # in parentheses on the right side of the UNION ALL.
    sql = f"""
    SELECT year, function, amount, per_fte, share, source
    FROM delta_spending_national_clean
    UNION ALL
    SELECT year, function, amount, per_fte, share, source FROM (
    {tail_national}
    )
    """
    return run_sql(sql, con)


def build_hr_staff_clean(
    con: duckdb.DuckDBPyConnection,
    years: list[int],
) -> pd.DataFrame:
    """hr_staff_clean — IPEDS HR admin vs faculty headcount + FTE, one row per unitid×year.

    admin_headcount  = STAFFCAT 1300 (Management), FTPT=1 (all staff), HRTOTLT.
    faculty_headcount = STAFFCAT 1210 (Instructional staff), FTPT=1, HRTOTLT.
    fte_total        = EFIA 12-month FTE (FTEUG + FTEGD) for that year.
    Clean window = 2012-13 SOC categories only (no pre-2012 crosswalk).
    """
    blocks = []
    for yr in years:
        hr_tbl = f"ipeds_hr_{yr}_raw"
        fte_tbl = f"ipeds_fte_{yr}_raw"
        blocks.append(
            f"""
        SELECT a.unitid, {yr} AS year, a.admin_headcount, f.faculty_headcount,
               (COALESCE(TRY_CAST(e.FTEUG AS DOUBLE),0) + COALESCE(TRY_CAST(e.FTEGD AS DOUBLE),0)) AS fte_total
        FROM (SELECT TRY_CAST(UNITID AS BIGINT) AS unitid,
                     SUM(TRY_CAST(HRTOTLT AS DOUBLE)) AS admin_headcount
              FROM {hr_tbl} WHERE STAFFCAT = 1300 AND FTPT = 1 GROUP BY UNITID) a
        FULL OUTER JOIN (SELECT TRY_CAST(UNITID AS BIGINT) AS unitid,
                     SUM(TRY_CAST(HRTOTLT AS DOUBLE)) AS faculty_headcount
              FROM {hr_tbl} WHERE STAFFCAT = 1210 AND FTPT = 1 GROUP BY UNITID) f
          ON a.unitid = f.unitid
        LEFT JOIN {fte_tbl} e
          ON COALESCE(a.unitid, f.unitid) = TRY_CAST(e.UNITID AS BIGINT)
        """
        )
    sql = "\nUNION ALL\n".join(blocks)
    # COALESCE the join key so a unit present in only one of admin/faculty still lands.
    sql = sql.replace("SELECT a.unitid, ", "SELECT COALESCE(a.unitid, f.unitid) AS unitid, ")
    return run_sql(f"SELECT * FROM ({sql}) ORDER BY year, unitid", con)


def build_hr_staff_national_clean(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """hr_staff_national_clean — one row per year: summed admin, faculty, FTE + admin_per_100_faculty."""
    sql = """
    SELECT year,
           SUM(admin_headcount)   AS admin_headcount,
           SUM(faculty_headcount) AS faculty_headcount,
           SUM(fte_total)         AS fte_total,
           100.0 * SUM(admin_headcount) / NULLIF(SUM(faculty_headcount), 0) AS admin_per_100_faculty
    FROM hr_staff_clean
    GROUP BY year
    ORDER BY year
    """
    return run_sql(sql, con)
