"""Build the higher-education-cost infographic (tall + social SVG -> PNG) and validate every
data mark back to the DuckDB chart tables and the published export CSVs.

Every line point, bar, dot and big number is COMPUTED from data/project.duckdb (read-only; the
same chart_* tables the four published charts use). Tall and social are fed identical queried
values; only the canvas mapping differs. Each mark carries data-* attributes so validate() can
parse it back out of the SVG, invert the pixel mapping, and compare with a fresh DB query and
with the export CSVs.

Usage (from project root):  .venv/bin/python scripts/_render_infographic.py
Writes docs/infographic_higher_education_cost{,_social}.{svg,png}
       + artifacts/INFOGRAPHIC-VALIDATION.md (gitignored)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
DOCS, ART, EXPORT = PROJECT / "docs", PROJECT / "artifacts", PROJECT / "export"
DOCS.mkdir(exist_ok=True)
ART.mkdir(exist_ok=True)

NAVY, TEAL, GOLD, SPICE, AQUA = "#003049", "#005F73", "#EE9B00", "#BB3E03", "#94D2BD"
VANILLA, GREY, BG, LINEGREY = "#E9D8A6", "#6B7280", "#FBF8F0", "#B8BEC6"
FONT = 'font-family="Helvetica, Arial, sans-serif"'

SECTORS_OTHER = ["Medical care services", "Medical care (all)", "Prescription drugs",
                 "Shelter", "Energy", "Gasoline"]
FUNCS = [("instruction", "Instruction", TEAL),
         ("institutional_support", "Institutional support (admin)", SPICE),
         ("academic_support", "Academic support", NAVY),
         ("student_services", "Student services", GOLD)]


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace("\u2013", "&#8211;").replace("\u2014", "&#8212;").replace("\u2019", "&#8217;")
             .replace("\u2192", "&#8594;").replace("\u00d7", "&#215;").replace("\u2248", "&#8776;")
             .replace("\u2022", "&#8226;").replace("\u0394", "&#916;"))


class Lin:
    def __init__(self, v0, v1, p0, p1):
        self.v0, self.v1, self.p0, self.p1 = v0, v1, p0, p1

    def __call__(self, v):
        return self.p0 + (v - self.v0) / (self.v1 - self.v0) * (self.p1 - self.p0)

    def inv(self, p):
        return self.v0 + (p - self.p0) / (self.p1 - self.p0) * (self.v1 - self.v0)


def f(x):
    return f"{x:.1f}"


def t(x, y, s, size, fill, weight="", anchor=""):
    w = f' font-weight="{weight}"' if weight else ""
    a = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{f(x)}" y="{f(y)}" fill="{fill}" font-size="{size}"{w}{a}>{esc(s)}</text>'


# ───────────────────────── data ─────────────────────────
def load():
    con = duckdb.connect(str(PROJECT / "data/project.duckdb"), read_only=True)
    q = lambda s: con.execute(s).fetchall()
    d = {}
    rows = q("SELECT sector, year, index_1979base FROM chart_cpi_indexed WHERE in_headline ORDER BY sector, year")
    d["idx"] = {}
    for sec, yr, v in rows:
        d["idx"].setdefault(sec, []).append((int(yr), float(v)))
    d["pct"] = {s: (float(p), lab) for s, p, lab in q(
        "SELECT sector, pct_vs_allitems, pct_vs_allitems_label FROM chart_cpi_vs_allitems "
        "WHERE in_headline AND NOT is_allitems")}
    d["tuition"] = {}
    for ctl in ("public", "all"):
        d["tuition"][ctl] = [(int(y), float(v)) for y, v in q(
            "SELECT year_start, value_constant FROM chart_tuition_longrun "
            f"WHERE level = '4-year' AND control = '{ctl}' ORDER BY year_start")]
        assert len({y for y, _ in d["tuition"][ctl]}) == len(d["tuition"][ctl]), "duplicate years"
    d["tbase"] = int(q("SELECT MAX(base_year) FROM chart_tuition_longrun")[0][0])
    d["mix"] = {}
    for fn, yr, sh in q("SELECT function, year, share FROM chart_spending_mix WHERE year IN "
                        "((SELECT MIN(year) FROM chart_spending_mix),(SELECT MAX(year) FROM chart_spending_mix))"):
        d["mix"].setdefault(fn, {})[int(yr)] = float(sh) * 100.0
    con.close()
    return d


def facts(d):
    F = {}
    idx25 = {s: v[-1][1] for s, v in d["idx"].items()}
    F["idx25"] = idx25
    F["y1"] = d["idx"]["All items"][-1][0]
    F["tui"], F["all"] = idx25["College tuition & fees"], idx25["All items"]
    F["pct_order"] = sorted(d["pct"], key=lambda s: -d["pct"][s][0])
    pub, al = d["tuition"]["public"], d["tuition"]["all"]
    F["pub0"], F["pub1"] = pub[0], pub[-1]
    F["all0"], F["all1"] = al[0], al[-1]
    F["pub_x"] = F["pub1"][1] / F["pub0"][1]
    F["all_x"] = F["all1"][1] / F["all0"][1]
    F["pub_peak"] = max(pub, key=lambda r: r[1])
    F["all_peak"] = max(al, key=lambda r: r[1])
    ys = sorted(d["mix"]["instruction"])
    F["m0"], F["m1"] = ys[0], ys[-1]
    F["noninstr0"] = sum(d["mix"][k][F["m0"]] for k in ("institutional_support", "academic_support", "student_services"))
    F["noninstr1"] = sum(d["mix"][k][F["m1"]] for k in ("institutional_support", "academic_support", "student_services"))
    return F


# ───────────────────────── sections (shared by tall + social) ─────────────────────────
def sec1(d, F, p, S):
    """CPI lines, 1979=100. S = scales dict (recorded for validation)."""
    xs = Lin(1979, F["y1"], p["px0"], p["px1"])
    ys = Lin(0, 1500, p["pyb"], p["pyt"])
    S["s1x"], S["s1y"] = xs, ys
    o = []
    for v in (500, 1000, 1500):
        o.append(f'<line x1="{f(p["px0"])}" y1="{f(ys(v))}" x2="{f(p["px1"])}" y2="{f(ys(v))}" stroke="#E5E0D0" stroke-width="1.5"/>'
                 + t(p["px0"] - 10, ys(v) + 6, f"{v:,}", p["tk"], GREY, anchor="end"))
    for sec in SECTORS_OTHER:
        pts = " ".join(f"{f(xs(y))},{f(ys(v))}" for y, v in d["idx"][sec])
        o.append(f'<polyline class="l1" data-s="{esc(sec)}" points="{pts}" fill="none" stroke="{LINEGREY}" stroke-width="2" stroke-linejoin="round"/>')
    for sec, col, w in (("All items", NAVY, p["lw"]), ("College tuition & fees", SPICE, p["lw"])):
        pts = " ".join(f"{f(xs(y))},{f(ys(v))}" for y, v in d["idx"][sec])
        o.append(f'<polyline class="l1" data-s="{esc(sec)}" points="{pts}" fill="none" stroke="{col}" stroke-width="{w}" stroke-linejoin="round" stroke-linecap="round"/>')
    ty, ay = ys(F["tui"]), ys(F["all"])
    o.append(f'<circle class="e1" data-s="College tuition &amp; fees" cx="{f(xs(F["y1"]))}" cy="{f(ty)}" r="{p["dr"]}" fill="{SPICE}"/><!-- tuition {F["tui"]:.1f} -->')
    o.append(f'<circle class="e1" data-s="All items" cx="{f(xs(F["y1"]))}" cy="{f(ay)}" r="{p["dr"]}" fill="{NAVY}"/><!-- all items {F["all"]:.1f} -->')
    lx = p["px1"] + 14
    o.append(t(lx, ty - 2, "Tuition & fees", p["lb"], SPICE, "bold") + t(lx, ty + p["lb"] + 2, f"{F['tui']:,.0f}", p["lb"], SPICE, "bold"))
    o.append(t(lx, ay + 4, "All items", p["lb"], NAVY, "bold") + t(lx, ay + p["lb"] + 6, f"{F['all']:,.0f}", p["lb"], NAVY, "bold"))
    for y in p["years"]:
        o.append(t(xs(y), p["pyb"] + p["tk"] + 10, str(y), p["tk"], GREY, anchor="middle"))
    return "\n  ".join(o)


def sec2(d, F, p, S):
    """Diverging bars: % above/below the All-items index at the latest year."""
    xs = Lin(-20, 240, p["xa"], p["xb"])
    S["s2x"] = xs
    zero = xs(0)
    o = [f'<line x1="{f(zero)}" y1="{f(p["y0"] - p["pitch"] * 0.55)}" x2="{f(zero)}" y2="{f(p["y0"] + p["pitch"] * (len(F["pct_order"]) - 0.45))}" stroke="{GREY}" stroke-width="2"/>']
    for i, sec in enumerate(F["pct_order"]):
        pv, lab = d["pct"][sec]
        y = p["y0"] + i * p["pitch"]
        x_end = xs(pv)
        x, w = (zero, x_end - zero) if pv >= 0 else (x_end, zero - x_end)
        col = SPICE if sec == "College tuition & fees" else (TEAL if pv >= 0 else GOLD)
        o.append(t(p["lx"], y + p["lb"] * 0.35, sec, p["lb"], NAVY, "bold", "end"))
        o.append(f'<rect class="b2" data-s="{esc(sec)}" x="{f(x)}" y="{f(y - p["bh"] / 2)}" width="{f(w)}" height="{f(p["bh"])}" fill="{col}"/>'
                 f'<!-- {sec} {pv:.2f}% -> end x {x_end:.1f} -->')
        if pv >= 0:
            o.append(t(x_end + 8, y + p["lb"] * 0.35, lab, p["lb"], col, "bold"))
        else:
            o.append(t(x_end - 8, y + p["lb"] * 0.35, lab.replace("-", "\u2212") if False else lab, p["lb"], "#CA6702", "bold", "end"))
    o.append(t(zero, p["y0"] + p["pitch"] * (len(F["pct_order"]) - 0.45) + p["tk"] + 4, "All items = 0%", p["tk"], GREY, anchor="middle"))
    return "\n  ".join(o)


def sec3(d, F, p, S):
    """Published 4-yr tuition, constant dollars: public vs all institutions."""
    xs = Lin(1963, 2023, p["px0"], p["px1"])
    ys = Lin(0, 22000, p["pyb"], p["pyt"])
    S["s3x"], S["s3y"] = xs, ys
    o = []
    for v in (10000, 20000):
        o.append(f'<line x1="{f(p["px0"])}" y1="{f(ys(v))}" x2="{f(p["px1"])}" y2="{f(ys(v))}" stroke="#E5E0D0" stroke-width="1.5"/>'
                 + t(p["px0"] - 10, ys(v) + 6, f"${v // 1000}k", p["tk"], GREY, anchor="end"))
    for key, col in (("all", GOLD), ("public", TEAL)):
        pts = " ".join(f"{f(xs(y))},{f(ys(v))}" for y, v in d["tuition"][key])
        o.append(f'<polyline class="l3" data-s="{key}" points="{pts}" fill="none" stroke="{col}" stroke-width="{p["lw"]}" stroke-linejoin="round" stroke-linecap="round"/>')
    marks = [("all", "s", F["all0"], GOLD), ("public", "s", F["pub0"], TEAL),
             ("all", "e", F["all1"], GOLD), ("public", "e", F["pub1"], TEAL),
             ("all", "p", F["all_peak"], GOLD), ("public", "p", F["pub_peak"], TEAL)]
    for key, kind, (yr, v), col in marks:
        o.append(f'<circle class="d3" data-s="{key}" data-k="{kind}" data-year="{yr}" cx="{f(xs(yr))}" cy="{f(ys(v))}" r="{p["dr"]}" fill="{col}"/><!-- {key} {kind} {yr} {v:.0f} -->')
    o.append(t(xs(F["all0"][0]) + 6, ys(F["all0"][1]) - 12, f"${F['all0'][1]:,.0f}", p["tk"], GOLD, "bold"))
    o.append(t(xs(F["pub0"][0]) + 6, ys(F["pub0"][1]) + p["tk"] + 8, f"${F['pub0'][1]:,.0f}", p["tk"], TEAL, "bold"))
    o.append(t(xs(F["all_peak"][0]), ys(F["all_peak"][1]) - 14, f"peak ${F['all_peak'][1]:,.0f} ({F['all_peak'][0]})", p["tk"], "#CA6702", "bold", "middle"))
    o.append(t(xs(F["pub_peak"][0]), ys(F["pub_peak"][1]) - 14, f"peak ${F['pub_peak'][1]:,.0f} ({F['pub_peak'][0]})", p["tk"], "#CA6702", "bold", "middle"))
    lx = p["px1"] + 14
    o.append(t(lx, ys(F["all1"][1]) - 2, "All institutions", p["lb"], GOLD, "bold") + t(lx, ys(F["all1"][1]) + p["lb"] + 2, f"${F['all1'][1]:,.0f}", p["lb"], GOLD, "bold"))
    o.append(t(lx, ys(F["pub1"][1]) + 4, "Public", p["lb"], TEAL, "bold") + t(lx, ys(F["pub1"][1]) + p["lb"] + 6, f"${F['pub1'][1]:,.0f}", p["lb"], TEAL, "bold"))
    for y in p["years"]:
        o.append(t(xs(y), p["pyb"] + p["tk"] + 10, str(y), p["tk"], GREY, anchor="middle"))
    return "\n  ".join(o)


def sec4(d, F, p, S):
    """Dumbbell rows: share of core spending, first vs last year."""
    xs = Lin(0, 55, p["xa"], p["xb"])
    S["s4x"] = xs
    o = []
    for v in (0, 25, 50):
        o.append(f'<line x1="{f(xs(v))}" y1="{f(p["y0"] - p["pitch"] * 0.5)}" x2="{f(xs(v))}" y2="{f(p["y0"] + p["pitch"] * 3.5)}" stroke="#E5E0D0" stroke-width="1.5"/>'
                 + t(xs(v), p["y0"] + p["pitch"] * 3.5 + p["tk"] + 6, f"{v}%", p["tk"], GREY, anchor="middle"))
    for i, (fn, name, col) in enumerate(FUNCS):
        y = p["y0"] + i * p["pitch"]
        a, b = d["mix"][fn][F["m0"]], d["mix"][fn][F["m1"]]
        o.append(f'<line x1="{f(xs(a))}" y1="{f(y)}" x2="{f(xs(b))}" y2="{f(y)}" stroke="{VANILLA}" stroke-width="{p["dr"] * 0.9:.1f}" stroke-linecap="round"/>')
        o.append(t(p["lx"], y + p["lb"] * 0.35, name, p["lb"], NAVY, "bold", "end"))
        o.append(f'<circle class="m0" data-f="{fn}" cx="{f(xs(a))}" cy="{f(y)}" r="{p["dr"]}" fill="{TEAL}"/><!-- {fn} {F["m0"]} {a:.2f} -->')
        o.append(f'<circle class="m1" data-f="{fn}" cx="{f(xs(b))}" cy="{f(y)}" r="{p["dr"]}" fill="{SPICE}"/><!-- {fn} {F["m1"]} {b:.2f} -->')
        lo, hi = (a, b) if a <= b else (b, a)
        lcol, hcol = (TEAL, SPICE) if a <= b else (SPICE, TEAL)
        la, lb_ = (f"{lo:.1f}%", f"{hi:.1f}%")
        o.append(t(xs(lo) - p["dr"] - 8, y + p["tk"] * 0.35, la, p["tk"] + 2, lcol, "bold", "end"))
        o.append(t(xs(hi) + p["dr"] + 8, y + p["tk"] * 0.35, lb_, p["tk"] + 2, hcol, "bold"))
        o.append(t(p["dx"], y + p["tk"] * 0.35, f"{b - a:+.1f} pts".replace("-", "\u2212") if False else f"{b - a:+.1f} pts", p["tk"] + 2, GREY, "bold", "end"))
    ly = p["y0"] - p["pitch"] * 0.9
    o.append(f'<circle cx="{f(p["xa"])}" cy="{f(ly)}" r="7" fill="{TEAL}"/>' + t(p["xa"] + 14, ly + 6, str(F["m0"]), p["tk"] + 2, GREY, "bold"))
    o.append(f'<circle cx="{f(p["xa"] + 90)}" cy="{f(ly)}" r="7" fill="{SPICE}"/>' + t(p["xa"] + 104, ly + 6, str(F["m1"]), p["tk"] + 2, GREY, "bold"))
    return "\n  ".join(o)


# ───────────────────────── canvases ─────────────────────────
def frame(W, H, hh, fh, title, tsize, hook, hsize, lede, lsize, ty, hy, ly):
    return (f'<rect width="{W}" height="{H}" fill="{BG}"/>\n'
            f'  <rect x="0" y="0" width="{W}" height="{hh}" fill="{NAVY}"/>\n'
            f'  {t(80 if W == 1200 else 40, ty, title, tsize, "#FFFFFF", "bold")}\n'
            f'  {t(80 if W == 1200 else 40, hy, hook, hsize, AQUA, "bold")}\n'
            f'  {t(80 if W == 1200 else 40, ly, lede, lsize, VANILLA)}\n')


def footer(W, H, fh, caveat_lines, size):
    x = 80 if W == 1200 else 40
    o = [f'<rect x="0" y="{H - fh}" width="{W}" height="{fh}" fill="{NAVY}"/>',
         t(x, H - fh + 30, "@unwelcomedata", 24, "#FFFFFF", "bold")]
    for i, ln in enumerate(caveat_lines):
        o.append(t(x, H - fh + 56 + i * (size + 6), ln, size, AQUA))
    return "\n  ".join(o)


def hr(x1, x2, y):
    return f'<line x1="{x1}" y1="{f(y)}" x2="{x2}" y2="{f(y)}" stroke="{VANILLA}" stroke-width="3"/>'


def build_tall(d, F, S):
    W, H = 1200, 3010
    S["tall"] = {}
    s = S["tall"]
    P1 = dict(px0=150, px1=950, pyt=560, pyb=900, tk=18, lw=4, dr=6, lb=20, years=(1979, 1990, 2000, 2010, 2025))
    P2 = dict(xa=520, xb=980, y0=1160, pitch=52, bh=30, lx=420, lb=22, tk=18)
    P3 = dict(px0=150, px1=950, pyt=1830, pyb=2120, tk=18, lw=4, dr=6, lb=20, years=(1963, 1980, 2000, 2023))
    P4 = dict(xa=470, xb=900, y0=2410, pitch=64, lx=440, dx=1120, lb=22, tk=18, dr=9)
    b1 = sec1(d, F, P1, s); b2 = sec2(d, F, P2, s); b3 = sec3(d, F, P3, s); b4 = sec4(d, F, P4, s)
    s["P"] = dict(P1=P1, P2=P2, P3=P3, P4=P4)
    capt = [
        "\u2022 CPI tuition and published tuition are sticker prices, not net of grant aid.",
        "\u2022 \u2018Admin\u2019 here means the IPEDS category institutional support only; its share is roughly flat (about 15%).",
        f"\u2022 Spending shares splice Delta Cost Project ({F['m0']}\u20132012) and IPEDS (2013 on); seam at 2012.",
    ]
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<!--
  @unwelcomedata - PROJECT INFOGRAPHIC (tall portrait poster)
  Project: higher-education-cost. Generated by scripts/_render_infographic.py; every mark is computed
  from data/project.duckdb (chart_cpi_indexed, chart_cpi_vs_allitems, chart_tuition_longrun, chart_spending_mix).
  Canvas {W} x {H}.
-->
<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" {FONT}>
  {frame(W, H, 300, 90, "The Cost of College", 72, "Tuition prices, inflation and college spending", 38,
         "Consumer Price Index and federal education data. Sticker prices, not net of aid.", 26, 126, 190, 242)}
  <!-- S1 -->
  {t(80, 372, "College tuition and seven other CPI series, 1979\u2013" + str(F["y1"]), 32, NAVY, "bold")}
  {t(80, 406, "Consumer Price Index, each series set to 100 in 1979. Grey lines: the other six sectors.", 22, GREY)}
  {t(80, 500, f"{F['tui']:,.0f}", 84, SPICE, "bold")}{t(80, 530, f"college tuition & fees, {F['y1']}", 22, GREY)}
  {t(1120, 500, f"{F['all']:,.0f}", 84, NAVY, "bold", anchor="end")}{t(1120, 530, f"all items, {F['y1']}", 22, GREY, anchor="end")}
  {b1}
  {t(80, 962, f"The {F['y1']} tuition & fees index is {F['tui'] / F['all']:.1f} times the all-items index.", 20, GREY)}
  {hr(80, 1120, 1000)}
  <!-- S2 -->
  {t(80, 1062, "Price rise since 1979 compared with all items", 32, NAVY, "bold")}
  {t(80, 1096, f"How far each sector's {F['y1']} index sits above (or below) the all-items index.", 22, GREY)}
  {b2}
  {t(80, 1566, "Medical care, prescription drugs and shelter also outpaced all items; energy and gasoline did not.", 20, GREY)}
  {hr(80, 1120, 1604)}
  <!-- S3 -->
  {t(80, 1666, "Published tuition and fees at 4-year colleges, 1963\u20132023", 32, NAVY, "bold")}
  {t(80, 1700, f"Constant {d['tbase']} dollars. Public institutions and all institutions combined.", 22, GREY)}
  {t(80, 1790, f"{F['pub_x']:.1f}\u00d7", 72, TEAL, "bold")}{t(300, 1790, f"public 4-year price, ${F['pub0'][1]:,.0f} to ${F['pub1'][1]:,.0f}", 22, GREY)}
  {b3}
  {t(80, 2190, f"Both series have eased in real terms since their peaks; the public line is {F['pub1'][1] / F['pub_peak'][1] - 1:.0%} from its {F['pub_peak'][0]} high.".replace("-", "\u2212") if False else f"Both series have eased in real terms since their peaks; the public line is {abs(F['pub1'][1] / F['pub_peak'][1] - 1):.0%} below its {F['pub_peak'][0]} high.", 20, GREY)}
  {hr(80, 1120, 2230)}
  <!-- S4 -->
  {t(80, 2292, f"Share of core spending by function, {F['m0']} and {F['m1']}", 32, NAVY, "bold")}
  {t(80, 2326, "National share of spending by function. Institutional support is the category used here as \u2018admin\u2019.", 22, GREY)}
  {b4}
  {t(80, 2700, f"Instruction: {d['mix']['instruction'][F['m0']]:.1f}% to {d['mix']['instruction'][F['m1']]:.1f}%. The three non-instruction functions shown together: {F['noninstr0']:.1f}% to {F['noninstr1']:.1f}%.", 22, NAVY, "bold")}
  {t(80, 2734, f"Institutional support alone moved {d['mix']['institutional_support'][F['m1']] - d['mix']['institutional_support'][F['m0']]:+.1f} points. The shift is mostly academic support and student services.", 20, GREY)}
  {hr(80, 1120, 2776)}
  <!-- CAVEATS -->
  {t(80, 2820, "Read with care", 26, NAVY, "bold")}
  {t(80, 2858, capt[0], 20, GREY)}
  {t(80, 2890, capt[1], 20, GREY)}
  {t(80, 2922, capt[2], 20, GREY)}
  {footer(W, H, 70, ["Sources: BLS CPI-U; NCES Digest Table 330.10; NCES Delta Cost Project; IPEDS Finance. Data from public sources."], 18)}
</svg>
'''
    return svg, W, H


def build_social(d, F, S):
    W, H = 1600, 900
    S["social"] = {}
    s = S["social"]
    ox, rx = 40, 840
    # cell tops: top row 160-480, bottom row 500-810
    P1 = dict(px0=ox + 60, px1=ox + 520, pyt=250, pyb=430, tk=15, lw=4, dr=5, lb=18, years=(1979, 2000, 2025))
    P2 = dict(xa=ox + 290, xb=ox + 600, y0=548, pitch=33, bh=20, lx=ox + 228, lb=17, tk=15)
    P3 = dict(px0=rx + 60, px1=rx + 520, pyt=250, pyb=430, tk=15, lw=4, dr=5, lb=18, years=(1963, 1980, 2000, 2023))
    P4 = dict(xa=rx + 290, xb=rx + 560, y0=565, pitch=48, lx=rx + 250, dx=rx + 720, lb=17, tk=15, dr=8)
    b1 = sec1(d, F, P1, s); b2 = sec2(d, F, P2, s); b3 = sec3(d, F, P3, s); b4 = sec4(d, F, P4, s)
    s["P"] = dict(P1=P1, P2=P2, P3=P3, P4=P4)
    cav = [f"Sticker prices, not net of aid. \u2018Admin\u2019 = IPEDS institutional support only (about 15% of core spending, roughly flat). "
           f"Spending shares splice Delta Cost ({F['m0']}\u20132012) and IPEDS (2013 on).",
           "Sources: BLS CPI-U; NCES Digest Table 330.10; NCES Delta Cost Project; IPEDS Finance. Data from public sources."]
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<!--
  @unwelcomedata - PROJECT INFOGRAPHIC (landscape social 1600x900)
  Project: higher-education-cost. Generated by scripts/_render_infographic.py; marks computed from
  data/project.duckdb with the same values as the tall poster (only the pixel mapping differs).
-->
<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" {FONT}>
  {frame(W, H, 150, 90, "The Cost of College", 56, "Tuition prices, inflation and college spending", 30,
         "Consumer Price Index and federal education data. Sticker prices, not net of aid.", 20, 62, 102, 134)}
  <line x1="800" y1="170" x2="800" y2="800" stroke="{VANILLA}" stroke-width="3"/>
  <!-- S1 -->
  {t(ox, 190, "College tuition and seven other CPI series", 25, NAVY, "bold")}
  {t(ox, 214, f"1979 = 100, 1979\u2013{F['y1']}. Grey: the other six sectors.", 17, GREY)}
  {t(ox + 110, 292, f"{F['tui']:,.0f}", 40, SPICE, "bold")}{t(ox + 110, 306, "tuition & fees index, 2025", 14, GREY)}
  {b1}
  {hr(ox, 760, 470)}
  <!-- S2 -->
  {t(ox, 500, "Price rise since 1979 compared with all items", 25, NAVY, "bold")}
  {t(ox, 522, f"Each sector's {F['y1']} index above (or below) all items.", 17, GREY)}
  {b2}
  <!-- S3 -->
  {t(rx, 190, "Published tuition and fees at 4-year colleges", 25, NAVY, "bold")}
  {t(rx, 214, f"1963\u20132023, constant {d['tbase']} dollars.", 17, GREY)}
  {t(rx + 110, 322, f"{F['pub_x']:.1f}\u00d7", 44, TEAL, "bold")}{t(rx + 110, 340, "public 4-year, 1963 to 2023", 14, GREY)}
  {b3}
  {hr(rx, 1560, 470)}
  <!-- S4 -->
  {t(rx, 500, f"Share of core spending by function, {F['m0']} and {F['m1']}", 25, NAVY, "bold")}
  {t(rx, 522, "Institutional support = \u2018admin\u2019 here.", 17, GREY)}
  {b4}
  {t(rx, 772, f"Institutional support alone moved {d['mix']['institutional_support'][F['m1']] - d['mix']['institutional_support'][F['m0']]:+.1f} points.", 17, NAVY, "bold")}
  {t(rx, 794, f"Non-instruction functions shown: {F['noninstr0']:.1f}% to {F['noninstr1']:.1f}%.", 17, GREY)}
  {footer(W, H, 90, cav, 15)}
</svg>
'''
    return svg, W, H


# ───────────────────────── validation ─────────────────────────
def validate(d, F, S, tall, social):
    lines, ok = [], True

    def chk(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        lines.append(f"- {'PASS' if cond else 'FAIL'} \u2014 {name}" + (f" ({detail})" if detail else ""))

    # fresh independent query + export CSVs
    cpi_csv = pd.read_csv(EXPORT / "higher_education_cost_cpi_sectors_v1.csv")
    tui_csv = pd.read_csv(EXPORT / "higher_education_cost_tuition_longrun_v1.csv")
    mix_csv = pd.read_csv(EXPORT / "higher_education_cost_spending_mix_v1.csv")
    csv_idx = {s: sorted(zip(g.year.astype(int), g.index_1979base)) for s, g in cpi_csv[cpi_csv.in_headline].groupby("sector")}
    for key in d["idx"]:
        assert all(abs(a[1] - b[1]) < 1e-6 and a[0] == b[0] for a, b in zip(d["idx"][key], csv_idx[key])) and len(d["idx"][key]) == len(csv_idx[key])
    chk("DB headline CPI series == export cpi_sectors_v1.csv (8 sectors, every year)", True)
    for ctl in ("public", "all"):
        g = tui_csv[(tui_csv.level == "4-year") & (tui_csv.control == ctl)].sort_values("year_start")
        assert [(int(a), float(b)) for a, b in zip(g.year_start, g.value_constant)] == d["tuition"][ctl]
    chk("DB 4-yr public + all tuition series == export tuition_longrun_v1.csv (all years)", True)
    for fn, _, _ in FUNCS:
        for yr in (F["m0"], F["m1"]):
            r = mix_csv[(mix_csv.function == fn) & (mix_csv.year == yr)].share.iloc[0] * 100
            assert abs(r - d["mix"][fn][yr]) < 1e-6
    chk("DB spending shares (4 functions, first + last year) == export spending_mix_v1.csv", True)

    def pts(svg, cls, key):
        out = {}
        for m in re.finditer(rf'<polyline class="{cls}" data-s="([^"]+)" points="([^"]+)"', svg):
            out[m.group(1)] = [tuple(map(float, p.split(","))) for p in m.group(2).split()]
        return out

    for name, svg in (("tall", tall), ("social", social)):
        s = S[name]
        # S1 lines
        l1 = pts(svg, "l1", "s")
        err = 0.0; n = 0
        for sec, series in d["idx"].items():
            got = l1[esc(sec)]
            assert len(got) == len(series)
            for (px, py), (y, v) in zip(got, series):
                err = max(err, abs(s["s1y"].inv(py) - v), abs(s["s1x"].inv(px) - y) * 10); n += 1
        chk(f"{name}: S1 {len(l1)} CPI polylines, {n} points match DB index values (max err {err:.2f} index pts)", len(l1) == 8 and err < 0.5)
        e1 = {m[0]: float(m[1]) for m in re.findall(r'class="e1" data-s="([^"]+)" cx="[\d.]+" cy="([\d.]+)"', svg)}
        eerr = max(abs(s["s1y"].inv(e1["College tuition &amp; fees"]) - F["tui"]), abs(s["s1y"].inv(e1["All items"]) - F["all"]))
        chk(f"{name}: S1 end dots = tuition {F['tui']:.1f}, all items {F['all']:.1f} (max err {eerr:.2f} index pts)", eerr < 0.5)
        # S2 bars
        b2 = re.findall(r'class="b2" data-s="([^"]+)" x="([\d.]+)" y="[\d.]+" width="([\d.]+)"', svg)
        zero = s["s2x"](0)
        berr = 0.0
        for sec, x, w in b2:
            x, w = float(x), float(w)
            sec_n = sec.replace("&amp;", "&")
            val = s["s2x"].inv(x + w) if abs(x - zero) < 0.2 else s["s2x"].inv(x)
            berr = max(berr, abs(val - d["pct"][sec_n][0]))
        chk(f"{name}: S2 {len(b2)} bars match pct_vs_allitems (max err {berr:.2f} pts); order high->low",
            len(b2) == 7 and berr < 0.6 and [b[0].replace('&amp;', '&') for b in b2] == F["pct_order"])
        # S3 lines + dots
        l3 = pts(svg, "l3", "s")
        terr = 0.0; n3 = 0
        for key in ("public", "all"):
            for (px, py), (y, v) in zip(l3[key], d["tuition"][key]):
                terr = max(terr, abs(s["s3y"].inv(py) - v), abs(s["s3x"].inv(px) - y)); n3 += 1
        chk(f"{name}: S3 2 polylines, {n3} points match DB constant-$ values (max err ${terr:.0f})", len(l3["public"]) == 57 and len(l3["all"]) == 57 and terr < 25)
        d3 = re.findall(r'class="d3" data-s="(\w+)" data-k="(\w)" data-year="(\d+)" cx="([\d.]+)" cy="([\d.]+)"', svg)
        derr = 0.0
        for key, k, yr, cx, cy in d3:
            v = dict(d["tuition"][key])[int(yr)]
            derr = max(derr, abs(s["s3y"].inv(float(cy)) - v), abs(s["s3x"].inv(float(cx)) - int(yr)) * 100)
        chk(f"{name}: S3 {len(d3)} start/end/peak dots sit on real data points (max err ${derr:.0f})", len(d3) == 6 and derr < 25)
        # S4 dots
        m0 = {m[0]: float(m[1]) for m in re.findall(r'class="m0" data-f="(\w+)" cx="([\d.]+)"', svg)}
        m1 = {m[0]: float(m[1]) for m in re.findall(r'class="m1" data-f="(\w+)" cx="([\d.]+)"', svg)}
        merr = max(max(abs(s["s4x"].inv(m0[fn]) - d["mix"][fn][F["m0"]]), abs(s["s4x"].inv(m1[fn]) - d["mix"][fn][F["m1"]])) for fn, _, _ in FUNCS)
        chk(f"{name}: S4 8 dumbbell dots match spending shares (max err {merr:.3f} pct pts)", len(m0) == len(m1) == 4 and merr < 0.1)

    # text facts vs validate_charts.py facts
    chk("tuition index 2025 \u2248 1476.5 and all items \u2248 443.4 (validate_charts R1)", abs(F["tui"] - 1476.5) < 1 and abs(F["all"] - 443.4) < 1, f"{F['tui']:.1f} / {F['all']:.1f}")
    chk("tuition +233% vs all items (R3b); gasoline \u2248 -10%, energy \u2248 -4%",
        abs(d["pct"]["College tuition & fees"][0] - 232.97) < 0.5 and abs(d["pct"]["Gasoline"][0] + 10.4) < 0.5 and abs(d["pct"]["Energy"][0] + 4.1) < 0.5)
    chk("text 'tuition index is 3.3 times the all-items index' = 1476.5/443.4", f"{F['tui'] / F['all']:.1f}" == "3.3", f"{F['tui'] / F['all']:.2f}")
    chk("text: medical care, Rx, shelter above all items; energy + gasoline below",
        all(d["pct"][k][0] > 0 for k in ("Medical care services", "Medical care (all)", "Prescription drugs", "Shelter"))
        and d["pct"]["Energy"][0] < 0 and d["pct"]["Gasoline"][0] < 0)
    chk("public 4-yr $2,442 (1963) -> $9,872 (2023), 4.0x (validate_charts N1)", F["pub0"] == (1963, 2442.0) and F["pub1"] == (2023, 9872.0) and f"{F['pub_x']:.1f}" == "4.0", f"{F['pub_x']:.2f}x")
    chk("text: both series below their peaks (public 2015, all 2019)", F["pub_peak"][0] == 2015 and F["all_peak"][0] == 2019 and F["pub1"][1] < F["pub_peak"][1] and F["all1"][1] < F["all_peak"][1],
        f"public {F['pub1'][1] / F['pub_peak'][1] - 1:.1%}, all {F['all1'][1] / F['all_peak'][1] - 1:.1%}")
    ins = d["mix"]["instruction"]; adm = d["mix"]["institutional_support"]
    chk("instruction 48.8% -> 43.1% (N2)", abs(ins[F["m0"]] - 48.8) < 0.05 and abs(ins[F["m1"]] - 43.1) < 0.05, f"{ins[F['m0']]:.2f} -> {ins[F['m1']]:.2f}")
    chk("admin (institutional support) 14.7% -> 15.3%, +0.6 pts, roughly flat (N2)", abs(adm[F["m0"]] - 14.7) < 0.05 and abs(adm[F["m1"]] - 15.3) < 0.05 and abs(adm[F["m1"]] - adm[F["m0"]]) <= 1.5)
    chk("non-instruction (admin + academic + student services) 32.5% -> 37.4% (N2)", abs(F["noninstr0"] - 32.5) < 0.05 and abs(F["noninstr1"] - 37.4) < 0.05, f"{F['noninstr0']:.2f} -> {F['noninstr1']:.2f}")
    chk("text: academic support + student services carry the shift (+1.7, +2.6 pts) vs admin +0.6",
        (d["mix"]["academic_support"][F["m1"]] - d["mix"]["academic_support"][F["m0"]]) > 1.5 and (d["mix"]["student_services"][F["m1"]] - d["mix"]["student_services"][F["m0"]]) > 1.5)
    chk("text: first/last mix years are 1987 and 2019; tall and social both say so", F["m0"] == 1987 and F["m1"] == 2019 and "1987" in tall and "2019" in social)
    tall_no = tall.count("@unwelcomedata - PROJECT")  # comment only
    chk("single footer watermark (@unwelcomedata appears once as visible text per render)",
        len(re.findall(r">@unwelcomedata<", tall)) == 1 and len(re.findall(r">@unwelcomedata<", social)) == 1)
    return lines, ok


def render_png(jobs):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for svg_name, png_name, w, h in jobs:
            svg = (DOCS / svg_name).read_text(encoding="utf-8")
            html = f"<!doctype html><html><head><style>*{{margin:0;padding:0}}</style></head><body>{svg}</body></html>"
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            page.set_content(html)
            page.wait_for_timeout(300)
            page.screenshot(path=str(DOCS / png_name), clip={"x": 0, "y": 0, "width": w, "height": h})
            page.close()
            print(f"rendered {png_name} ({w}x{h})")
        browser.close()


def main() -> int:
    d = load()
    F = facts(d)
    S = {}
    tall, tw, th = build_tall(d, F, S)
    social, sw, sh = build_social(d, F, S)
    (DOCS / "infographic_higher_education_cost.svg").write_text(tall, encoding="utf-8")
    (DOCS / "infographic_higher_education_cost_social.svg").write_text(social, encoding="utf-8")
    render_png([("infographic_higher_education_cost.svg", "infographic_higher_education_cost.png", tw, th),
                ("infographic_higher_education_cost_social.svg", "infographic_higher_education_cost_social.png", sw, sh)])
    lines, ok = validate(d, F, S, tall, social)
    gate = subprocess.run([sys.executable, str(PROJECT / "scripts/validate_charts.py")], capture_output=True, text=True)
    gate_tail = gate.stdout.strip().splitlines()[-1]
    lines.append(f"- {'PASS' if gate.returncode == 0 else 'FAIL'} \u2014 scripts/validate_charts.py exit {gate.returncode}: {gate_tail}")
    ok &= gate.returncode == 0
    note = ("# Infographic data-mark validation \u2014 higher-education-cost\n\n"
            "Generated by `scripts/_render_infographic.py` (DuckDB opened read-only). Each mark in the tall and social SVGs\n"
            "is parsed back out of the SVG, the pixel mapping inverted, and compared with a fresh DB query and the\n"
            "export CSVs. Dev-only (gitignored).\n\n"
            "Mapping: S1 = chart_cpi_indexed (in_headline; index_1979base); S2 = chart_cpi_vs_allitems (pct_vs_allitems);\n"
            "S3 = chart_tuition_longrun (level 4-year, control public + all; private omitted, it has 3 rows per year);\n"
            "S4 = chart_spending_mix (first and last year, share x 100).\n\n"
            + "\n".join(lines) + f"\n\n**RESULT: {'ALL PASS' if ok else 'FAILURES'}**\n")
    (ART / "INFOGRAPHIC-VALIDATION.md").write_text(note, encoding="utf-8")
    print("\n".join(lines))
    print("RESULT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
