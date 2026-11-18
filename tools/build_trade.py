"""
Build clean tables from the Census files in 01_data/raw/us_imports.

    python tools/build_trade.py

Writes 01_data/processed/thread_count.duckdb:
  bronze.us_imports       every row as published (one country, HS6 product and month), numbers typed
  silver.imports          countries only (no world total), with chapter and month as a date
  silver.world            the total for all countries, same grain
  gold.share_hs6          each country's share of US imports, by HS6 product and month
  gold.country_month      each country's totals by chapter and month: value, duty, effective tariff, share
  gold.tariff_hs6_year    effective tariff by country, HS6 and year (duty paid / dutiable value, and / total value)
  gold.collection_log     which files were read, and when they were collected
Also writes CSV copies of the gold tables to 01_data/processed/.

Effective tariff = calculated duty / value. Calculated duty is what Customs computed on imports for consumption,
so it reflects the rates actually applied, including any extra tariffs in force that month.
"""
import glob, json, os
import duckdb
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "01_data", "raw", "us_imports")
PROC = os.path.join(ROOT, "01_data", "processed")
LAKE = os.path.join(PROC, "thread_count.duckdb")
NUM = ["GEN_VAL_MO", "CON_VAL_MO", "DUT_VAL_MO", "CAL_DUT_MO", "CON_QY1_MO"]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    os.makedirs(PROC, exist_ok=True)
    rows, log = [], []
    files = sorted(glob.glob(os.path.join(RAW, "*_*_*.json")))
    print(f"Reading {len(files)} files...", flush=True)
    for path in files:
        name = os.path.basename(path)[:-5]
        country, chapter, year = name.rsplit("_", 2)
        doc = json.load(open(path, encoding="utf-8"))
        data = doc.get("data") or []
        if len(data) < 2:
            log.append((country, chapter, int(year), 0, doc.get("source"), doc.get("retrieved")))
            continue
        head = data[0]
        ix = {}
        for i, h in enumerate(head):          # the API repeats some columns; keep the first
            ix.setdefault(h, i)
        for r in data[1:]:
            rows.append((country, r[ix["CTY_CODE"]], chapter, r[ix["I_COMMODITY"]], r[ix["I_COMMODITY_SDESC"]],
                         r[ix["time"]], *[num(r[ix[k]]) for k in NUM], r[ix["UNIT_QY1"]]))
        log.append((country, chapter, int(year), len(data) - 1, doc.get("source"), doc.get("retrieved")))
    if not rows:
        raise SystemExit("No data in 01_data/raw/us_imports. Run tools/collect_us_imports.py first.")

    con = duckdb.connect(LAKE)
    for s in ("bronze", "silver", "gold"):
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")
    print(f"Read {len(log)} files, {len(rows):,} rows. Building tables...", flush=True)
    df = pd.DataFrame(rows, columns=["country", "cty_code", "chapter", "hs6", "description", "ym", "gen_value",
                                     "con_value", "dutiable_value", "duty", "quantity", "unit"])
    con.register("df_rows", df)
    con.execute("CREATE OR REPLACE TABLE bronze.us_imports AS SELECT * FROM df_rows")
    con.unregister("df_rows")
    con.execute("""CREATE OR REPLACE TABLE gold.collection_log (
        country VARCHAR, chapter VARCHAR, year INTEGER, rows INTEGER, source VARCHAR, retrieved VARCHAR)""")
    con.register("df_log", pd.DataFrame(log, columns=["country", "chapter", "year", "rows", "source", "retrieved"]))
    con.execute("INSERT INTO gold.collection_log SELECT * FROM df_log")

    con.execute("""
    CREATE OR REPLACE TABLE silver.imports AS
    SELECT country, chapter, hs6, any_value(description) AS description,
           CAST(ym || '-01' AS DATE) AS month,
           sum(gen_value) AS gen_value, sum(con_value) AS con_value,
           sum(dutiable_value) AS dutiable_value, sum(duty) AS duty
    FROM bronze.us_imports WHERE country <> 'world'
    GROUP BY country, chapter, hs6, month""")
    con.execute("""
    CREATE OR REPLACE TABLE silver.world AS
    SELECT chapter, hs6, any_value(description) AS description, CAST(ym || '-01' AS DATE) AS month,
           sum(gen_value) AS gen_value, sum(con_value) AS con_value,
           sum(dutiable_value) AS dutiable_value, sum(duty) AS duty
    FROM bronze.us_imports WHERE country = 'world'
    GROUP BY chapter, hs6, month""")

    con.execute("""
    CREATE OR REPLACE TABLE gold.share_hs6 AS
    SELECT i.country, i.chapter, i.hs6, i.description, i.month, i.gen_value, w.gen_value AS world_value,
           i.gen_value / nullif(w.gen_value, 0) AS share
    FROM silver.imports i JOIN silver.world w USING (chapter, hs6, month)""")
    con.execute("""
    CREATE OR REPLACE TABLE gold.country_month AS
    WITH c AS (SELECT country, chapter, month, sum(gen_value) gen_value, sum(con_value) con_value,
                      sum(dutiable_value) dutiable_value, sum(duty) duty
               FROM silver.imports GROUP BY ALL),
         w AS (SELECT chapter, month, sum(gen_value) world_value, sum(duty) world_duty, sum(con_value) world_con
               FROM silver.world GROUP BY ALL)
    SELECT c.*, w.world_value, c.gen_value / nullif(w.world_value, 0) AS share,
           c.duty / nullif(c.con_value, 0) AS tariff_on_value,
           c.duty / nullif(c.dutiable_value, 0) AS tariff_on_dutiable,
           w.world_duty / nullif(w.world_con, 0) AS world_tariff_on_value
    FROM c JOIN w USING (chapter, month) ORDER BY country, chapter, month""")
    con.execute("""
    CREATE OR REPLACE TABLE gold.tariff_hs6_year AS
    SELECT country, chapter, hs6, any_value(description) AS description, year(month) AS year,
           sum(con_value) AS con_value, sum(dutiable_value) AS dutiable_value, sum(duty) AS duty,
           sum(duty) / nullif(sum(con_value), 0) AS tariff_on_value,
           sum(duty) / nullif(sum(dutiable_value), 0) AS tariff_on_dutiable
    FROM silver.imports GROUP BY country, chapter, hs6, year""")

    for t in ("bronze.us_imports", "silver.imports", "silver.world", "gold.share_hs6", "gold.country_month",
              "gold.tariff_hs6_year", "gold.collection_log"):
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        if t.startswith("gold"):
            con.execute(f"COPY {t} TO '{os.path.join(PROC, t.split('.')[1] + '.csv').replace(chr(92), '/')}' (HEADER)")
        print(f"  {t:24s} {n:>10,} rows")

    print("\nBangladesh, chapters 61 and 62 together, by year: US imports ($bn), share, effective tariff")
    for r in con.execute("""
        SELECT year(month) y, sum(gen_value)/1e9, sum(gen_value)/sum(world_value), sum(duty)/sum(con_value)
        FROM gold.country_month WHERE country='bangladesh' AND chapter IN ('61','62')
        GROUP BY y ORDER BY y""").fetchall():
        print(f"  {r[0]}  ${r[1]:6.2f}bn  share {r[2]*100:5.1f}%  tariff {r[3]*100:5.1f}%")
    con.close()
    print(f"\nSaved {LAKE}")


if __name__ == "__main__":
    main()
