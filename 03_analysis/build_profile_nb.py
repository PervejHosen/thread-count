"""Build and run 03_analysis/01_data_profile_and_share.ipynb.

Run from the project folder:
    python 03_analysis/build_profile_nb.py
Needs: duckdb, pandas, matplotlib, nbformat, nbconvert (ipykernel).
"""
from pathlib import Path
import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

HERE = Path(__file__).resolve().parent
OUT = HERE / "01_data_profile_and_share.ipynb"

md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell

cells = [
md("""# Thread Count 01: data profile and market share

US imports of apparel (HS chapters 61 knitted and 62 woven) from Bangladesh and seven competitors, January 2017 to September 2026, from the US Census Bureau international trade API.

Questions in this notebook:

1. Is the data complete and does it add up?
2. How has each country's share of US apparel imports moved?
3. China lost about 9 share points between 2024 and 2026. Which products did it lose, and who picked them up?
4. How do Bangladesh's tariff steps line up with the dated tariff actions?

Comparisons use January to September of each year, because 2026 data stops in September."""),
code("""import duckdb, pandas as pd, matplotlib.pyplot as plt, matplotlib.dates as mdates
from pathlib import Path

ROOT = Path.cwd().parent if Path.cwd().name == "03_analysis" else Path.cwd()
con = duckdb.connect(str(ROOT / "01_data/processed/thread_count.duckdb"), read_only=True)
events = pd.read_csv(ROOT / "01_data/reference/tariff_events.csv", parse_dates=["date"])

GREEN, OCHRE, TOMATO, SLATE, LIGHT = "#1D4A35", "#B87318", "#F2462E", "#7D8D99", "#3B8A60"
COLORS = {"bangladesh": TOMATO, "china": SLATE, "vietnam": GREEN, "india": OCHRE,
          "cambodia": LIGHT, "indonesia": "#A88B5C", "pakistan": "#9AA5A0", "sri_lanka": "#C9B89A"}
plt.rcParams.update({"figure.facecolor": "#F7F1E6", "axes.facecolor": "#F7F1E6", "axes.edgecolor": "#DCCFB6",
                     "axes.grid": True, "grid.color": "#E6DCC8", "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 10, "text.color": "#16382A",
                     "axes.labelcolor": "#4F5E52", "xtick.color": "#4F5E52", "ytick.color": "#4F5E52"})
pd.set_option("display.float_format", "{:,.2f}".format)
APPAREL = "('61','62')"
YEARS = (2024, 2025, 2026)"""),

md("## 1. Data profile"),
code("""con.sql(\"\"\"
select country, count(*) as rows, count(distinct hs6) as hs6_codes,
       min(month) as first_month, max(month) as last_month, count(distinct month) as months,
       round(sum(gen_value)/1e9, 1) as gen_value_bn
from silver.imports group by country order by gen_value_bn desc
\"\"\").df()"""),
code("""# Gaps: every country x chapter should have all months from Jan 2017 to Sep 2026
gaps = con.sql(\"\"\"
with expected as (select count(distinct month) n from silver.world)
select country, chapter, count(distinct month) as months, (select n from expected) as expected
from silver.imports group by all having count(distinct month) < (select n from expected)
\"\"\").df()
gaps"""),
md("Only Sri Lanka footwear (chapter 64) misses one month, which is outside the apparel scope here."),
code("""# Checks: no negative values, duty never above value, and the eight countries never exceed the world total
checks = con.sql(f\"\"\"
select
  (select count(*) from silver.imports where gen_value < 0 or con_value < 0 or duty < 0) as negative_rows,
  (select count(*) from silver.imports where duty > con_value and con_value > 0) as duty_above_value,
  (select count(*) from (
      select s.hs6, s.month, sum(s.gen_value) v, any_value(w.gen_value) wv
      from silver.imports s join silver.world w using (hs6, month)
      group by all having sum(s.gen_value) > any_value(w.gen_value) * 1.001)) as hs6_months_over_world
\"\"\").df()
checks"""),
md("""All 14 rows where duty is above value are China in April and May 2025, when China's extra tariff reached 145%. They are real, not errors."""),
code("""# General imports vs imports for consumption: how far apart are the two value measures?
con.sql(f\"\"\"
select year(month) as year, round(sum(gen_value)/1e9,2) as general_bn, round(sum(con_value)/1e9,2) as consumption_bn,
       round(100*(sum(con_value)/sum(gen_value)-1),2) as pct_gap
from silver.imports where chapter in {APPAREL} and country='bangladesh' group by 1 order by 1
\"\"\").df()"""),
md("""Shares use **general imports** (goods arriving in the US). Tariff rates use **imports for consumption** and calculated duty, the same basis Census uses for duty. The two differ by goods held in bonded warehouses; for Bangladesh apparel the gap is small, as the table shows."""),

md("## 2. Share of US apparel imports"),
code("""share_year = con.sql(f\"\"\"
with c as (select country, year(month) y, sum(gen_value) v from silver.imports
           where chapter in {APPAREL} and month(month) <= 9 group by all),
     w as (select year(month) y, sum(gen_value) wv from silver.world
           where chapter in {APPAREL} and month(month) <= 9 group by all)
select country, y as year, v/1e9 as value_bn, 100*v/wv as share_pct from c join w using (y)
\"\"\").df()
world_year = con.sql(f\"\"\"select year(month) as yr, sum(gen_value)/1e9 world_bn from silver.world
  where chapter in {APPAREL} and month(month)<=9 group by 1 order by 1\"\"\").df().rename(columns={\"yr\": \"year\"})
tbl = share_year.pivot(index="country", columns="year", values="share_pct").sort_values(2026, ascending=False)
tbl["change_24_26"] = tbl[2026] - tbl[2024]
tbl[[2017, 2019, 2022, 2024, 2025, 2026, "change_24_26"]]"""),
code("""world_year.set_index("year").T"""),
code("""val = share_year.pivot(index="country", columns="year", values="value_bn")
val[[2024, 2025, 2026]].assign(change_bn=val[2026]-val[2024]).sort_values(2026, ascending=False)"""),
code("""# Rolling 12 month share, monthly
m = con.sql(f\"\"\"
with c as (select country, month, sum(gen_value) v from silver.imports where chapter in {APPAREL} group by all),
     w as (select month, sum(gen_value) wv from silver.world where chapter in {APPAREL} group by all)
select country, month, v, wv from c join w using (month) order by country, month
\"\"\").df()
m["month"] = pd.to_datetime(m["month"])
m = m.sort_values(["country", "month"])
m["v12"] = m.groupby("country")["v"].transform(lambda s: s.rolling(12).sum())
m["wv12"] = m.groupby("country")["wv"].transform(lambda s: s.rolling(12).sum())
m["share12"] = 100 * m["v12"] / m["wv12"]

fig, ax = plt.subplots(figsize=(10, 4.8))
for ctry in ["china", "vietnam", "bangladesh", "india", "cambodia", "indonesia"]:
    d = m[m.country == ctry]
    ax.plot(d.month, d.share12, color=COLORS[ctry], lw=2.4 if ctry == "bangladesh" else 1.6, label=ctry.title())
ax.axvline(pd.Timestamp("2025-04-05"), color=TOMATO, lw=0.8, ls=":")
ax.text(pd.Timestamp("2025-04-20"), ax.get_ylim()[1]*0.95, "10% tariff on all\\n5 Apr 2025", fontsize=8, color="#B8301C")
ax.set_ylabel("Share of US apparel imports, %, rolling 12 months")
ax.set_title("China's share keeps falling; Vietnam, Bangladesh and Cambodia gain", loc="left", fontsize=12, color=GREEN)
ax.legend(ncol=3, frameon=False, fontsize=9); ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y")); plt.tight_layout(); plt.show()"""),

md("""## 3. Where China's lost share went

A country's share of all apparel imports is the sum, over every HS6 product, of its imports of that product divided by total apparel imports. So the change in share between January to September 2024 and 2026 splits exactly into one contribution per product. Positive means the product added share points to that country."""),
code("""hs = con.sql(f\"\"\"
with c as (select country, hs6, any_value(description) descr, year(month) y, sum(gen_value) v
           from silver.imports where chapter in {APPAREL} and month(month)<=9 and year(month) in (2024, 2026)
           group by country, hs6, y),
     w as (select year(month) y, sum(gen_value) wv from silver.world
           where chapter in {APPAREL} and month(month)<=9 and year(month) in (2024, 2026) group by 1)
select country, hs6, descr, y, v, 100*v/wv as pts from c join w using (y)
\"\"\").df()
contrib = hs.pivot_table(index=["country", "hs6"], columns="y", values="pts", aggfunc="sum").fillna(0)
contrib["pts_change"] = contrib[2026] - contrib[2024]
contrib = contrib.reset_index()
desc = hs.groupby("hs6")["descr"].first()

# Check: product contributions add up to the headline share change
check = contrib.groupby("country")["pts_change"].sum().rename("sum_of_products").to_frame()
check["headline"] = tbl["change_24_26"]
assert (check["sum_of_products"] - check["headline"]).abs().max() < 1e-6
check.sort_values("headline")"""),
code("""china = contrib[contrib.country == "china"].nsmallest(15, "pts_change")
top = china.hs6.tolist()
gain = contrib[contrib.hs6.isin(top)].pivot(index="hs6", columns="country", values="pts_change").loc[top]
gain.insert(0, "product", desc.loc[top].str.slice(0, 45).values)
cols = ["product", "china", "vietnam", "bangladesh", "cambodia", "indonesia", "india", "pakistan", "sri_lanka"]
gain[cols]"""),
md("""Countries outside the eight, and changes in each product's weight in total imports, take up the rest, so a row does not sum to zero. Totals over China's 15 biggest losses:"""),
code("""tot = gain.drop(columns=["product"]).sum().sort_values()
print(f"China lost {-tot['china']:.2f} share points in these 15 products "
      f"(of {-tbl.loc['china','change_24_26']:.2f} in total).")
tot.to_frame("share_points_in_top15")"""),
code("""fig, ax = plt.subplots(figsize=(10, 6)); ax.set_axisbelow(True); ax.grid(axis="y", visible=False)
g = gain.set_index(gain["product"].str.slice(0, 40).str.strip())[["china", "vietnam", "bangladesh", "cambodia", "indonesia", "india"]]
left_neg = pd.Series(0.0, index=g.index); left_pos = pd.Series(0.0, index=g.index)
for c in g.columns:
    v = g[c]; neg = v.clip(upper=0); pos = v.clip(lower=0)
    ax.barh(g.index, neg, left=left_neg, color=COLORS[c], label=c.title()); left_neg += neg
    ax.barh(g.index, pos, left=left_pos, color=COLORS[c]); left_pos += pos
ax.invert_yaxis(); ax.axvline(0, color=GREEN, lw=0.8)
ax.set_xlabel("Share points of all US apparel imports, Jan to Sep 2026 vs 2024")
ax.set_title("China's 15 biggest losses, and who gained in the same products", loc="left", fontsize=12, color=GREEN)
ax.legend(frameon=False, fontsize=9, loc="lower left"); plt.tight_layout(); plt.show()"""),
code("""# Bangladesh: which products drove its gain?
bd = contrib[contrib.country == "bangladesh"].sort_values("pts_change", ascending=False)
bd = bd.assign(product=desc.loc[bd.hs6].str.slice(0, 50).values)
pd.concat([bd.head(10), bd.tail(5)])[["hs6", "product", 2024, 2026, "pts_change"]]"""),

md("## 4. Bangladesh's tariff, month by month, against the dated actions"),
code("""t = con.sql(\"\"\"
select month, country, sum(duty)/sum(con_value)*100 as tariff_pct
from silver.imports where chapter in ('61','62') and country in ('bangladesh','vietnam','china','india','cambodia')
group by all order by month
\"\"\").df()
t["month"] = pd.to_datetime(t["month"])
fig, ax = plt.subplots(figsize=(10, 4.8))
for ctry in ["china", "india", "vietnam", "cambodia", "bangladesh"]:
    d = t[(t.country == ctry) & (t.month >= "2024-01-01")]
    ax.plot(d.month, d.tariff_pct, color=COLORS[ctry], lw=2.6 if ctry == "bangladesh" else 1.4, label=ctry.title())
marks = [("2025-04-05", "10% on all"), ("2025-08-07", "BD 20%"), ("2026-02-24", "Court ruling,\\n10% temporary"),
         ("2026-07-24", "Section 301\\nBD 10%")]
for d, lab in marks:
    ax.axvline(pd.Timestamp(d), color=TOMATO, lw=0.8, ls=":")
    ax.text(pd.Timestamp(d), 71, " " + lab, fontsize=8, color="#B8301C", va="top")
ax.set_ylim(0, 74); ax.set_ylabel("Duty collected as % of import value")
ax.set_title("Effective tariff on apparel, monthly, ch 61 and 62", loc="left", fontsize=12, color=GREEN)
ax.legend(ncol=5, frameon=False, fontsize=9, loc="lower center", bbox_to_anchor=(0.5, -0.28)); plt.tight_layout(); plt.show()"""),
code("""bdt = t[t.country == "bangladesh"].set_index("month")["tariff_pct"]
bdt["2025-01-01":].round(1).to_frame().T"""),
code("""events[["date", "country", "measure", "rate_added"]]"""),
md("""## Notes for the next notebook

* Shares above are January to September only. Full years come once October to December 2026 data is out.
* The monthly tariff rate counts duty when goods enter, so a new rate shows up gradually as goods already in transit clear customs.
* India's rate fell in February 2026, before the court ruling. The events list doesn't explain that yet; it needs a sourced date.
* Next: effective tariff by product and country, how much of each country's exports face the highest rates, and seasonality."""),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})
ExecutePreprocessor(timeout=600, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(HERE)}})
nbf.write(nb, OUT)
print("wrote", OUT)
