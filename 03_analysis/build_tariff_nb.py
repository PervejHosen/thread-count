"""Build and run 03_analysis/02_tariff_exposure_seasonality.ipynb.

Run from the project folder:
    python 03_analysis/build_tariff_nb.py
"""
from pathlib import Path
import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

HERE = Path(__file__).resolve().parent
OUT = HERE / "02_tariff_exposure_seasonality.ipynb"
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

cells = [
md("""# Thread Count 02: tariff by product, exposure and seasonality

Effective tariff here means duty collected divided by the value of imports for consumption, for apparel (HS chapters 61 and 62).

Three periods, matching the tariff actions in `01_data/reference/tariff_events.csv`:

| Period | Months | What applied |
|---|---|---|
| Before | Jan to Dec 2024 | normal duty only |
| Peak | Oct 2025 to Jan 2026 | country reciprocal rates (Bangladesh 20%) on top of normal duty |
| Now | Mar to Sep 2026 | flat 10% (Section 122, then Section 301 from 24 July) on top of normal duty |

Questions:

1. How much did each country's tariff rise in each period, and how much of that is product mix?
2. Which Bangladesh products pay the most?
3. How much of each country's apparel is cotton, the fibre the US-cotton route in the February 2026 deal would affect?
4. How concentrated are Bangladesh's exports?
5. Is there a seasonal pattern, and did importers bring orders forward before the tariffs?"""),
code("""import duckdb, pandas as pd, numpy as np, matplotlib.pyplot as plt
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == "03_analysis" else Path.cwd()
con = duckdb.connect(str(ROOT / "01_data/processed/thread_count.duckdb"), read_only=True)

GREEN, OCHRE, TOMATO, SLATE, LIGHT = "#1D4A35", "#B87318", "#F2462E", "#7D8D99", "#3B8A60"
COLORS = {"bangladesh": TOMATO, "china": SLATE, "vietnam": GREEN, "india": OCHRE,
          "cambodia": LIGHT, "indonesia": "#A88B5C", "pakistan": "#9AA5A0", "sri_lanka": "#C9B89A"}
plt.rcParams.update({"figure.facecolor": "#F7F1E6", "axes.facecolor": "#F7F1E6", "axes.edgecolor": "#DCCFB6",
                     "axes.grid": True, "grid.color": "#E6DCC8", "axes.spines.top": False, "axes.axisbelow": True,
                     "axes.spines.right": False, "font.size": 10, "text.color": "#16382A",
                     "axes.labelcolor": "#4F5E52", "xtick.color": "#4F5E52", "ytick.color": "#4F5E52"})
pd.set_option("display.float_format", "{:,.2f}".format)

df = con.sql(\"\"\"
select country, hs6, any_value(description) as descr, month, sum(con_value) as con_value,
       sum(gen_value) as gen_value, sum(duty) as duty
from silver.imports where chapter in ('61','62') group by country, hs6, month
\"\"\").df()
df["month"] = pd.to_datetime(df["month"])

def period(m):
    if m.year == 2024: return "before"
    if pd.Timestamp("2025-10-01") <= m <= pd.Timestamp("2026-01-01"): return "peak"
    if pd.Timestamp("2026-03-01") <= m <= pd.Timestamp("2026-09-01"): return "now"
    return None
df["period"] = df["month"].map(period)

def fibre(d):
    d = str(d).upper()
    if any(k in d for k in ["COTTON", "COTT", " COT", "COT,"]): return "cotton"
    if any(k in d for k in ["MAN-MADE", "MANMADE", "MMF", "MM F", "SYN", "ARTIF", "MAN MADE"]): return "man-made"
    if any(k in d for k in ["WOOL", "KASHMIR", "ANIMAL HAIR", "SILK"]): return "wool or silk"
    return "other or mixed"
desc = df.groupby("hs6")["descr"].first()
fib = desc.map(fibre)
df["fibre"] = df["hs6"].map(fib)
fib.value_counts()"""),
md("""Fibre comes from the Census short description of each HS6 code, so it is approximate. "Other or mixed" covers codes described as "other textile materials" or with no fibre named."""),

md("## 1. Tariff rise by country, and how much is product mix"),
code("""p = df.dropna(subset=["period"]).groupby(["country", "period"])[["con_value", "duty"]].sum()
rate = (100 * p["duty"] / p["con_value"]).unstack()[["before", "peak", "now"]]
rate["added_peak"] = rate["peak"] - rate["before"]
rate["added_now"] = rate["now"] - rate["before"]
rate.sort_values("now")"""),
md("""The "before" rate differs by country mostly because of product mix: US normal duty is higher on man-made fibre garments than on cotton ones. To separate mix from country treatment, the next cell prices each country's own product mix at the **average rate the seven countries other than China paid** for each product in that period. China is left out of the benchmark because its goods also carry Section 301 duties from 2018 and 2019. The world average is not used as the benchmark, because it includes duty-free partners such as Mexico and Central America."""),
code("""pp = df.dropna(subset=["period"])
peer = pp[pp.country != "china"].groupby(["hs6", "period"])[["duty", "con_value"]].sum()
peer = (peer["duty"] / peer["con_value"]).rename("peer_rate").reset_index()
mix = pp.groupby(["country", "period", "hs6"])["con_value"].sum().rename("v").reset_index()
mix["wt"] = mix["v"] / mix.groupby(["country", "period"])["v"].transform("sum")
m2 = mix.merge(peer, on=["hs6", "period"]).assign(x=lambda d: d.wt * d.peer_rate)
mix_rate = (100 * m2.groupby(["country", "period"])["x"].sum()).unstack()[["before", "peak", "now"]]
cmp_ = pd.DataFrame({"actual_before": rate["before"], "mix_only_before": mix_rate["before"],
                     "actual_peak": rate["peak"], "mix_only_peak": mix_rate["peak"],
                     "actual_now": rate["now"], "mix_only_now": mix_rate["now"]})
for per in ["before", "peak", "now"]:
    cmp_[f"treatment_{per}"] = cmp_[f"actual_{per}"] - cmp_[f"mix_only_{per}"]
cmp_.sort_values("actual_now")"""),
md("""`mix_only` is what the country would pay if every product were charged the seven-country average rate for that product, so it reflects product mix alone. `treatment` is the rest: the country-specific part of the tariff. Before 2025 the seven paid the same normal duty, so their treatment is close to zero (any gap comes from finer product detail below HS6), while China sits above because of the 2018 to 2019 Section 301 duties."""),
code("""fig, ax = plt.subplots(figsize=(10, 4.6))
order = rate.sort_values("now").index
x = np.arange(len(order)); bw = 0.27
for i, (col, colr, lab) in enumerate([("before", "#C3CDBF", "2024"), ("peak", OCHRE, "Oct 2025 to Jan 2026"), ("now", GREEN, "Mar to Sep 2026")]):
    ax.bar(x + (i - 1) * bw, rate.loc[order, col], bw, color=colr, label=lab)
ax.set_xticks(x, [c.replace("_", " ").title() for c in order])
for lbl in ax.get_xticklabels():
    if lbl.get_text() == "Bangladesh": lbl.set_color("#B8301C"); lbl.set_fontweight("bold")
ax.set_ylabel("Effective tariff, %")
ax.set_title("Apparel tariff by country, three periods", loc="left", fontsize=12, color=GREEN)
ax.legend(frameon=False, ncol=3, fontsize=9); plt.tight_layout(); plt.show()"""),

md("## 2. Bangladesh: what each main product pays"),
code("""bd = df[(df.country == "bangladesh") & df.period.notna()].groupby(["hs6", "period"])[["con_value", "duty"]].sum().unstack()
bdr = pd.DataFrame({
    "product": desc.loc[bd.index].str.slice(0, 48).values,
    "fibre": fib.loc[bd.index].values,
    "value_now_m": bd[("con_value", "now")] / 1e6,
    "rate_before": 100 * bd[("duty", "before")] / bd[("con_value", "before")],
    "rate_now": 100 * bd[("duty", "now")] / bd[("con_value", "now")],
}, index=bd.index)
bdr["share_of_bd_now"] = 100 * bdr["value_now_m"] / bdr["value_now_m"].sum()
bdr.sort_values("value_now_m", ascending=False).head(15)"""),
code("""top = bdr.sort_values("value_now_m", ascending=False).head(25)
fig, ax = plt.subplots(figsize=(10, 5))
for f, colr in [("cotton", GREEN), ("man-made", TOMATO), ("wool or silk", OCHRE), ("other or mixed", SLATE)]:
    d = top[top.fibre == f]
    ax.scatter(d.rate_now, d.value_now_m, s=60, color=colr, label=f, alpha=.9)
for h, r in top.head(6).iterrows():
    ax.annotate(r["product"][:30].capitalize() + f" ({r.fibre})", (r.rate_now, r.value_now_m), fontsize=7.5, xytext=(5, 3), textcoords="offset points")
ax.set_xlabel("Effective tariff, Mar to Sep 2026, %"); ax.set_ylabel("Imports, Mar to Sep 2026, $m")
ax.set_title("Bangladesh's 25 biggest apparel products: man-made fibre pays more", loc="left", fontsize=12, color=GREEN)
ax.legend(frameon=False, fontsize=9); plt.tight_layout(); plt.show()"""),

md("## 3. Fibre mix: how much is cotton"),
code("""f = df[df.month.dt.year.isin([2024, 2026]) & (df.month.dt.month <= 9)]
fm = f.groupby(["country", f.month.dt.year.rename("year"), "fibre"])["gen_value"].sum()
fm = (100 * fm / fm.groupby(level=[0, 1]).transform("sum")).unstack("fibre")
fm.xs(2026, level="year").sort_values("cotton", ascending=False)"""),
code("""fr = df[df.period == "now"].groupby(["country", "fibre"])[["duty", "con_value"]].sum()
(100 * fr["duty"] / fr["con_value"]).unstack().round(1)"""),
md("""Cotton garments pay less normal duty than man-made fibre ones, so a cotton-heavy country starts lower. The February 2026 agreement promised a zero reciprocal rate for garments made with US cotton or man-made fibre; with the IEEPA tariffs struck down two weeks later, how that applies to the current 10% is not yet clear."""),

md("## 4. Exposure and concentration"),
code("""now = df[df.period == "now"].groupby(["country", "hs6"])[["con_value", "duty"]].sum()
now["rate"] = now["duty"] / now["con_value"]
exp = now.groupby("country").apply(lambda d: pd.Series({
    "value_now_bn": d.con_value.sum() / 1e9,
    "pct_value_rate_ge_30": 100 * d.loc[d.rate >= .30, "con_value"].sum() / d.con_value.sum(),
    "top5_share_pct": 100 * d.con_value.nlargest(5).sum() / d.con_value.sum(),
    "top10_share_pct": 100 * d.con_value.nlargest(10).sum() / d.con_value.sum(),
    "hhi": ((d.con_value / d.con_value.sum()) ** 2).sum() * 10000,
}))
exp.sort_values("top10_share_pct", ascending=False)"""),
md("""HHI is the Herfindahl index of the country's own product mix (0 to 10,000; higher means fewer products carry the exports)."""),

md("## 5. Seasonality and front-loading"),
code("""bdm = df[df.country == "bangladesh"].groupby("month")["gen_value"].sum()
base = bdm["2017":"2024"]
idx = base.groupby(base.index.month).mean() / base.mean() * 100
fig, ax = plt.subplots(figsize=(10, 3.8))
ax.bar(range(1, 13), idx.values, color=GREEN)
ax.axhline(100, color=TOMATO, lw=.8, ls=":")
ax.set_xticks(range(1, 13), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
ax.set_ylabel("Index, average month = 100")
ax.set_title("Bangladesh apparel arrivals by month, 2017 to 2024 average", loc="left", fontsize=12, color=GREEN)
plt.tight_layout(); plt.show()
idx.round(0).to_frame("index").T"""),
code("""# Year on year change by month, 2025 and 2026, Bangladesh vs China vs world
def yoy(series):
    s = series.copy(); return 100 * (s / s.shift(12) - 1)
g = df.groupby(["country", "month"])["gen_value"].sum().unstack(0)
wm = con.sql("select month, sum(gen_value) v from silver.world where chapter in ('61','62') group by 1 order by 1").df()
wm["month"] = pd.to_datetime(wm["month"]); g["world"] = wm.set_index("month")["v"]
y = g.apply(yoy)["2025-01-01":]
fig, ax = plt.subplots(figsize=(10, 4.2))
for c, colr, lw in [("world", SLATE, 1.4), ("china", "#B0BAC2", 1.4), ("vietnam", GREEN, 1.4), ("bangladesh", TOMATO, 2.6)]:
    ax.plot(y.index, y[c], color=colr, lw=lw, label=c.title())
ax.axhline(0, color=GREEN, lw=.8)
for d in ["2025-04-05", "2025-08-07", "2026-02-24"]:
    ax.axvline(pd.Timestamp(d), color=TOMATO, lw=.8, ls=":")
ax.set_ylabel("Change vs same month a year earlier, %")
ax.set_title("Bangladesh imports surged in early 2025, before the tariffs, then fell below 2025 levels", loc="left", fontsize=12, color=GREEN)
ax.legend(frameon=False, ncol=4, fontsize=9); plt.tight_layout(); plt.show()
y[["bangladesh", "vietnam", "china", "world"]].round(1).T"""),
md("""## Notes for the next steps

* All rates are duty collected on goods entered, so refunds of IEEPA duty (still in court) are not reflected.
* Fibre is approximate, from short descriptions.
* Next: a forecast of Bangladesh's share and value under the current 10% rate, then the review script and the Power BI report."""),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})
ExecutePreprocessor(timeout=600, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(HERE)}})
nbf.write(nb, OUT)
print("wrote", OUT)
