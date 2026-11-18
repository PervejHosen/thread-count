"""Recompute Thread Count's headline numbers a second way and compare.

This reads the raw Census JSON files directly with the standard library only. It does not
use DuckDB, pandas or anything built by tools/build_trade.py, so a mistake in the pipeline
or the notebooks shows up here as a MISMATCH.

Run from the project folder:
    python 05_review/verify.py
Writes 05_review/verify_report.md and exits with code 1 if any check fails.
"""
import glob, json, os, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "01_data", "raw", "us_imports")
REPORT = os.path.join(ROOT, "05_review", "verify_report.md")
APPAREL = ("61", "62")

# rows[(country, hs6, "YYYY-MM")] = [gen, con, duty]; world kept under country "world"
rows = defaultdict(lambda: [0.0, 0.0, 0.0])
files = 0
for path in sorted(glob.glob(os.path.join(RAW, "*_*_*.json"))):
    country, chapter, year = os.path.basename(path)[:-5].rsplit("_", 2)
    if chapter not in APPAREL:
        continue
    files += 1
    data = json.load(open(path, encoding="utf-8"))["data"]
    head = data[0]
    col = {name: head.index(name) for name in head}  # index() gives the first of any repeated name
    for r in data[1:]:
        if r[col["COMM_LVL"]] != "HS6":
            continue
        key = (country, r[col["I_COMMODITY"]], r[col["time"]])
        acc = rows[key]
        for i, name in enumerate(("GEN_VAL_MO", "CON_VAL_MO", "CAL_DUT_MO")):
            v = r[col[name]]
            acc[i] += float(v) if v not in (None, "", "-") else 0.0

def total(country, months, field):
    i = {"gen": 0, "con": 1, "duty": 2}[field]
    return sum(v[i] for (c, h, m), v in rows.items() if c == country and m in months)

def months(year, upto=12):
    return {f"{year}-{m:02d}" for m in range(1, upto + 1)}

def jan_sep(y): return months(y, 9)
PEAK = {"2025-10", "2025-11", "2025-12", "2026-01"}
NOW = {f"2026-{m:02d}" for m in range(3, 10)}
COUNTRIES = ["bangladesh", "china", "vietnam", "india", "cambodia", "indonesia", "pakistan", "sri_lanka"]

checks = []  # (name, expected, got, tolerance, unit)
def check(name, expected, got, tol, unit=""):
    checks.append((name, expected, got, tol, unit))

# 1. World and Bangladesh values
for y, exp in [(2024, 60.05), (2025, 60.95), (2026, 57.33)]:
    check(f"World apparel imports Jan-Sep {y}", exp, total("world", jan_sep(y), "gen") / 1e9, 0.006, "$bn")
for y, exp in [(2024, 5.20), (2025, 6.17), (2026, 5.90)]:
    check(f"Bangladesh Jan-Sep {y}", exp, total("bangladesh", jan_sep(y), "gen") / 1e9, 0.006, "$bn")
for y, exp in [(2024, 7.05), (2025, 7.88)]:
    check(f"Bangladesh full year {y}", exp, total("bangladesh", months(y), "gen") / 1e9, 0.006, "$bn")

# 2. Shares Jan-Sep
expected_share = {
    2024: {"vietnam": 18.40, "china": 21.82, "bangladesh": 8.67, "cambodia": 4.70, "indonesia": 5.31,
           "india": 6.09, "pakistan": 2.67, "sri_lanka": 2.08},
    2026: {"vietnam": 21.97, "china": 12.55, "bangladesh": 10.30, "cambodia": 6.74, "indonesia": 6.43,
           "india": 5.40, "pakistan": 3.07, "sri_lanka": 2.28},
}
for y, exp in expected_share.items():
    w = total("world", jan_sep(y), "gen")
    for c, e in exp.items():
        check(f"Share {c} Jan-Sep {y}", e, 100 * total(c, jan_sep(y), "gen") / w, 0.006, "%")

# 3. Bangladesh monthly effective tariff
for m, e in [("2025-01", 16.8), ("2025-10", 35.9), ("2026-01", 36.3), ("2026-02", 33.1),
             ("2026-03", 24.8), ("2026-09", 26.2)]:
    check(f"Bangladesh tariff {m}", e, 100 * total("bangladesh", {m}, "duty") / total("bangladesh", {m}, "con"), 0.051, "%")

# 4. Period tariff by country
for c, e in [("india", 23.41), ("bangladesh", 25.61), ("vietnam", 28.50), ("china", 31.46)]:
    check(f"Tariff now (Mar-Sep 2026) {c}", e, 100 * total(c, NOW, "duty") / total(c, NOW, "con"), 0.006, "%")
for c, e in [("india", 63.07), ("bangladesh", 36.04)]:
    check(f"Tariff peak (Oct 2025-Jan 2026) {c}", e, 100 * total(c, PEAK, "duty") / total(c, PEAK, "con"), 0.006, "%")

# 5. Concentration: Bangladesh top 5 products, share of con value Mar-Sep 2026
by_hs = defaultdict(float)
for (c, h, m), v in rows.items():
    if c == "bangladesh" and m in NOW:
        by_hs[h] += v[1]
top5 = sum(sorted(by_hs.values(), reverse=True)[:5]) / sum(by_hs.values())
check("Bangladesh top 5 products share now", 52.20, 100 * top5, 0.006, "%")

# 6. Product contribution: women's cotton trousers (620462), Bangladesh, share points 2024 to 2026
def pts(country, hs6, y):
    w = total("world", jan_sep(y), "gen")
    return 100 * sum(v[0] for (c, h, m), v in rows.items() if c == country and h == hs6 and m in jan_sep(y)) / w
check("Bangladesh 620462 share-point change", 0.42, pts("bangladesh", "620462", 2026) - pts("bangladesh", "620462", 2024), 0.006, "pts")

# 7. China's 15 biggest product losses add up to 4.76 points
hs_codes = {h for (c, h, m) in rows if c == "china"}
loss = sorted(pts("china", h, 2026) - pts("china", h, 2024) for h in hs_codes)[:15]
check("China loss in its 15 biggest products", -4.76, sum(loss), 0.006, "pts")

# Report
lines = ["# Thread Count verification", "",
         f"Raw files read: {files} (chapters 61 and 62). Checks: {len(checks)}.", "",
         "| Check | Expected | Recomputed | Result |", "|---|---|---|---|"]
fails = 0
for name, e, g, tol, unit in checks:
    ok = abs(e - g) <= tol
    fails += not ok
    lines.append(f"| {name} | {e:,.2f} {unit} | {g:,.3f} {unit} | {'ok' if ok else 'MISMATCH'} |")
lines += ["", f"**{len(checks) - fails} of {len(checks)} checks match.**"]

# External comparison with OTEXA (US Commerce Department textile office), reported by the
# Financial Express on its 2025 figures. OTEXA's apparel definition is wider than HS 61 + 62
# (it adds some garments and accessories from other chapters), so levels differ; growth should be close.
otexa = {"bd_2024": 7.34, "bd_2025": 8.20, "world_2024": 79.23, "world_2025": 77.88}
ours = {"bd_2024": total("bangladesh", months(2024), "gen") / 1e9, "bd_2025": total("bangladesh", months(2025), "gen") / 1e9,
        "world_2024": total("world", months(2024), "gen") / 1e9, "world_2025": total("world", months(2025), "gen") / 1e9}
g = lambda d, k: 100 * (d[k + "_2025"] / d[k + "_2024"] - 1)
lines += ["", "## Outside check: OTEXA 2025 (not pass or fail)", "",
          "| Figure | OTEXA | Ours (HS 61 + 62) |", "|---|---|---|",
          f"| Bangladesh 2025 | $8.20bn | ${ours['bd_2025']:.2f}bn |",
          f"| Bangladesh growth 2024 to 2025 | 11.75% | {g(ours, 'bd'):.2f}% |",
          f"| US total 2025 | $77.88bn | ${ours['world_2025']:.2f}bn |",
          f"| US total growth 2024 to 2025 | -1.70% | {g(ours, 'world'):.2f}% |",
          f"| Bangladesh share 2025 | {100*8.20/77.88:.1f}% | {100*ours['bd_2025']/ours['world_2025']:.1f}% |",
          "", "Source: https://thefinancialexpress.com.bd/economy/bangladesh/2025-rmg-exports-to-us-increase-1175pc"]
open(REPORT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
for l in lines[4:]:
    print(l)
sys.exit(1 if fails else 0)
