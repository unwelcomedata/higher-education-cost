#!/usr/bin/env python3
"""Pre-publish validation — re-check the chart data before anything goes public.

Re-derives, straight from the project DuckDB, the headline facts the four
published "big education" charts show, and confirms the published export CSVs
still match their DuckDB source tables (no drift). Also confirms the social/web
chart sets stay in parity when rendered outputs are present.

The four published charts (from scripts/_build_nb_06_viz_social.py):
  R1  01_big_education_indexed.png      ← chart_cpi_indexed      (export: cpi_sectors_v1)
  R3b 02_outran_inflation_diverging.png ← chart_cpi_vs_allitems  (export: cpi_sectors_v1)
  N1  03_tuition_since_1963.png         ← chart_tuition_longrun  (export: tuition_longrun_v1)
  N2  04_spending_mix.png               ← chart_spending_mix     (export: spending_mix_v1)

Exit code 0 = safe to publish. Non-zero = do NOT publish.

Usage:
    .venv/bin/python scripts/validate_charts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

# --- resolve the project root (folder containing config.yaml) ---------------
PROJECT = Path(__file__).resolve().parent
while not (PROJECT / "config.yaml").exists() and PROJECT != PROJECT.parent:
    PROJECT = PROJECT.parent

DB = PROJECT / "data" / "project.duckdb"
EXPORT = PROJECT / "export"

failures: list[str] = []
checks: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        checks.append(f"  PASS  {name}")
    else:
        failures.append(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


# Export CSV ↔ DuckDB source-table pairs that back the four published charts.
# Each export table is a verbatim 1:1 copy of its chart_* source table, so a
# column-and-value match proves the published data has not drifted from the DB.
EXPORT_PAIRS = [
    ("higher_education_cost_cpi_sectors_v1", "chart_cpi_indexed"),      # R1 + R3b data
    ("higher_education_cost_tuition_longrun_v1", "chart_tuition_longrun"),  # N1 data
    ("higher_education_cost_spending_mix_v1", "chart_spending_mix"),    # N2 data
]


def _frames_match(csv_df: pd.DataFrame, db_df: pd.DataFrame) -> tuple[bool, str]:
    """True when the export CSV and the DuckDB table carry the same data.

    Columns must match (same names, same order); row counts must match; and the
    sorted numeric/text content must be equal to a small float tolerance (so
    CSV round-tripping of floats doesn't trip the check).
    """
    if list(csv_df.columns) != list(db_df.columns):
        return False, f"columns differ: csv={list(csv_df.columns)} db={list(db_df.columns)}"
    if len(csv_df) != len(db_df):
        return False, f"row count differ: csv={len(csv_df)} db={len(db_df)}"
    cols = list(db_df.columns)
    a = csv_df[cols].sort_values(cols).reset_index(drop=True)
    b = db_df[cols].sort_values(cols).reset_index(drop=True)
    for col in cols:
        sa, sb = a[col], b[col]
        numeric = (pd.api.types.is_numeric_dtype(sb) and pd.api.types.is_numeric_dtype(sa)
                   and not pd.api.types.is_bool_dtype(sb)
                   and not pd.api.types.is_bool_dtype(sa))
        if numeric:
            if not ((sa.fillna(-9e18) - sb.fillna(-9e18)).abs() <= 1e-6).all():
                return False, f"numeric drift in {col!r}"
        else:
            if not (sa.astype(str).fillna("") == sb.astype(str).fillna("")).all():
                return False, f"value drift in {col!r}"
    return True, ""


def main() -> int:
    if not DB.exists():
        print(f"DuckDB not found at {DB} — run 03-prepare (or scripts/reproduce.py) first.")
        return 2

    con = duckdb.connect(str(DB), read_only=True)
    have = {r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables").fetchall()}
    for _, t in EXPORT_PAIRS:
        if t not in have:
            check(f"source table {t} present", False,
                  "run 03-prepare to build the chart tables")

    latest = int(con.execute("SELECT MAX(year) FROM chart_cpi_indexed").fetchone()[0])

    # ── R1 (chart_cpi_indexed): the steepest-line "big education" chart ──────
    r1 = con.execute(
        "SELECT sector, index_1979base FROM chart_cpi_indexed "
        f"WHERE in_headline AND year = {latest} ORDER BY index_1979base DESC"
    ).df()
    check("R1: exactly 8 headline sectors on the 1979 window",
          len(r1) == 8, f"got {len(r1)}")
    top_sector = r1.iloc[0]["sector"]
    top_index = float(r1.iloc[0]["index_1979base"])
    check("R1: steepest sector is College tuition & fees",
          top_sector == "College tuition & fees", f"got {top_sector!r}")
    check("R1: college tuition index ≈ 1476 (1979=100)",
          abs(top_index - 1476.5) < 1.0, f"got {top_index:.1f}")
    allitems_index = float(
        r1[r1["sector"] == "All items"]["index_1979base"].iloc[0])
    check("R1: All Items index ≈ 443 (1979=100)",
          abs(allitems_index - 443.4) < 1.0, f"got {allitems_index:.1f}")

    # ── R3b (chart_cpi_vs_allitems): out-ran-general-inflation diverging bar ─
    r3 = con.execute(
        "SELECT sector, pct_vs_allitems, pct_vs_allitems_label, is_allitems "
        "FROM chart_cpi_vs_allitems WHERE in_headline ORDER BY pct_vs_allitems DESC"
    ).df()
    top3 = r3.iloc[0]
    check("R3b: largest positive bar is College tuition & fees",
          top3["sector"] == "College tuition & fees", f"got {top3['sector']!r}")
    check("R3b: tuition out-ran All Items by ≈ +233%",
          abs(float(top3["pct_vs_allitems"]) - 232.97) < 0.5,
          f"got {float(top3['pct_vs_allitems']):.1f}%")
    check("R3b: tuition bar label is '+233%'",
          str(top3["pct_vs_allitems_label"]) == "+233%",
          f"got {top3['pct_vs_allitems_label']!r}")
    allitems_row = r3[r3["is_allitems"]].iloc[0]
    check("R3b: All Items is the zero reference (= 0%)",
          abs(float(allitems_row["pct_vs_allitems"])) < 1e-6,
          f"got {float(allitems_row['pct_vs_allitems']):.3f}")
    gas = float(r3[r3["sector"] == "Gasoline"]["pct_vs_allitems"].iloc[0])
    eng = float(r3[r3["sector"] == "Energy"]["pct_vs_allitems"].iloc[0])
    check("R3b: gasoline LAGGED general inflation ≈ -10%",
          abs(gas + 10.4) < 0.5, f"got {gas:.1f}%")
    check("R3b: energy LAGGED general inflation ≈ -4%",
          abs(eng + 4.1) < 0.5, f"got {eng:.1f}%")

    # ── N1 (chart_tuition_longrun): real published 4-yr tuition, 1963 → latest ─
    n1 = con.execute(
        "SELECT year_start, control, value_constant FROM chart_tuition_longrun "
        "WHERE level = '4-year' ORDER BY year_start"
    ).df()
    pub = n1[n1["control"] == "public"].sort_values("year_start")
    first_year = int(pub.iloc[0]["year_start"])
    last_year = int(pub.iloc[-1]["year_start"])
    pub_first = float(pub.iloc[0]["value_constant"])
    pub_last = float(pub.iloc[-1]["value_constant"])
    check("N1: public 4-yr series starts 1963-64", first_year == 1963,
          f"got {first_year}")
    check("N1: public 4-yr constant-$ ≈ $2,442 in 1963-64",
          abs(pub_first - 2442.0) < 1.0, f"got ${pub_first:,.0f}")
    check("N1: public 4-yr constant-$ ≈ $9,872 at latest",
          abs(pub_last - 9872.0) < 1.0, f"got ${pub_last:,.0f}")
    ratio = pub_last / pub_first
    check("N1: public 4-yr real tuition roughly quadrupled (~4×)",
          abs(ratio - 4.0) < 0.3, f"got {ratio:.2f}×")
    # Private is the top line at the latest year among the three controls.
    latest_by_control = n1[n1["year_start"] == last_year].set_index("control")["value_constant"]
    top_control = latest_by_control.idxmax()
    check("N1: private is the top (most expensive) line",
          top_control == "private", f"got {top_control!r}")

    # ── N2 (chart_spending_mix): instruction vs non-instructional, honest cut ─
    mix_y0 = int(con.execute("SELECT MIN(year) FROM chart_spending_mix").fetchone()[0])
    mix_y1 = int(con.execute("SELECT MAX(year) FROM chart_spending_mix").fetchone()[0])
    mix = con.execute(
        f"SELECT year, function, share FROM chart_spending_mix "
        f"WHERE year IN ({mix_y0}, {mix_y1})"
    ).df()
    piv = mix.pivot_table(index="year", columns="function", values="share") * 100.0
    noninstr = ["institutional_support", "academic_support", "student_services"]
    instr_y0 = float(piv.loc[mix_y0, "instruction"])
    instr_y1 = float(piv.loc[mix_y1, "instruction"])
    admin_y0 = float(piv.loc[mix_y0, "institutional_support"])
    admin_y1 = float(piv.loc[mix_y1, "institutional_support"])
    noninstr_y0 = float(piv.loc[mix_y0, noninstr].sum())
    noninstr_y1 = float(piv.loc[mix_y1, noninstr].sum())
    check(f"N2: instruction share {mix_y0}→{mix_y1} ≈ 48.8% → 43.1%",
          abs(instr_y0 - 48.8) < 0.1 and abs(instr_y1 - 43.1) < 0.1,
          f"got {instr_y0:.1f}% → {instr_y1:.1f}%")
    check(f"N2: institutional support (admin) ≈ flat 14.7% → 15.3%",
          abs(admin_y0 - 14.7) < 0.1 and abs(admin_y1 - 15.3) < 0.1,
          f"got {admin_y0:.1f}% → {admin_y1:.1f}%")
    check("N2: admin share change is small (≤ ~1 pp) — the honest 'admin flat' nuance",
          abs(admin_y1 - admin_y0) <= 1.5, f"got {admin_y1 - admin_y0:+.1f} pp")
    check(f"N2: non-instructional share rose 32.5% → 37.4%",
          abs(noninstr_y0 - 32.5) < 0.1 and abs(noninstr_y1 - 37.4) < 0.1,
          f"got {noninstr_y0:.1f}% → {noninstr_y1:.1f}%")
    check("N2: non-instructional grew more than instruction (slopes diverge)",
          (noninstr_y1 - noninstr_y0) > 0 and (instr_y1 - instr_y0) < 0,
          f"instr {instr_y1 - instr_y0:+.1f} pp, non-instr {noninstr_y1 - noninstr_y0:+.1f} pp")

    # ── Export-vs-DB drift: each published CSV must match its DuckDB table ───
    for export_name, table in EXPORT_PAIRS:
        csv_path = EXPORT / f"{export_name}.csv"
        if not csv_path.exists():
            check(f"export {export_name}.csv present", False, f"missing {csv_path}")
            continue
        if table not in have:
            continue
        csv_df = pd.read_csv(csv_path)
        db_df = con.execute(f"SELECT * FROM {table}").df()
        ok, detail = _frames_match(csv_df, db_df)
        check(f"export {export_name}.csv matches DuckDB {table} (no drift)", ok, detail)

    con.close()

    # ── Social vs web chart parity (when rendered outputs are present) ───────
    social_dir = PROJECT / "outputs" / "social"
    web_dir = PROJECT / "outputs" / "web"
    social = sorted(social_dir.glob("*.png")) if social_dir.exists() else []
    if social and web_dir.exists():
        s_names = {p.name for p in social}
        w_names = {p.name for p in web_dir.glob("*.png")}
        check("social and web sets cover the same filenames", s_names == w_names,
              f"only social: {sorted(s_names - w_names)}; only web: {sorted(w_names - s_names)}")
        check("exactly the 4 published charts rendered", len(w_names) == 4,
              f"got {sorted(w_names)}")
        try:
            from PIL import Image
            # Every web chart uses the web canvas WIDTH (1664). Height is the
            # landscape default (936) unless a chart sets a deliberate custom
            # height (the R3b diverging bar is 760 in BOTH targets); so assert
            # width == 1664 and per-chart height parity with the social render,
            # rather than a single fixed canvas size.
            widths = {Image.open(p).size[0] for p in web_dir.glob("*.png")}
            check("every web chart uses the web width (1664)", widths == {1664},
                  f"unexpected widths: {sorted(widths)}")
            # A web chart is either the standard landscape web canvas height
            # (936) or, for a chart with a deliberate custom height, the SAME
            # height as its social render (the R3b bar is 760 in both).
            bad_height = []
            for p in web_dir.glob("*.png"):
                wh = Image.open(p).size[1]
                s = social_dir / p.name
                sh = Image.open(s).size[1] if s.exists() else None
                if wh != 936 and wh != sh:
                    bad_height.append(f"{p.name}=web{wh}/social{sh}")
            check("web height is 936 (standard) or matches a custom social height",
                  not bad_height, f"unexpected: {bad_height}")
        except ImportError:
            pass

    print("Pre-publish chart-data validation — higher-education-cost")
    print("=" * 62)
    for line in checks:
        print(line)
    for line in failures:
        print(line)
    print("=" * 62)
    if failures:
        print(f"RESULT: {len(failures)} FAILURE(S) — DO NOT PUBLISH.")
        return 1
    print(f"RESULT: all {len(checks)} checks passed — safe to publish.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
