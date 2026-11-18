"""
Collect US imports of textiles, apparel and footwear from Bangladesh and its competitors, by product and month.

Source: US Census Bureau, International Trade API (official, free, no login).
    https://api.census.gov/data/timeseries/intltrade/imports/hs
The API now needs a free key: request one at https://api.census.gov/data/key_signup.html (arrives by email),
then add a line CENSUS_KEY=your_key to .env (never commit it).

Each call asks for one country, one HS chapter and one year, at HS6 detail, with:
    value (general imports and imports for consumption), dutiable value, calculated duty, quantity and unit.
Calculated duty / dutiable value gives the tariff actually paid, product by product, month by month.

    python tools/collect_us_imports.py --test          # one call, prints a few rows
    python tools/collect_us_imports.py                 # all countries, chapters 61-64, 2017 to now

Output: 01_data/raw/us_imports/{country}_{chapter}_{year}.json and _log.csv. Files already saved are skipped.
"""
import argparse, csv, json, os, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "01_data", "raw", "us_imports")
BASES = ["https://api.census.gov/data/timeseries/intltrade/imports/hs",
         "https://api.census.gov/data/timeseries/intltrade/imports/hsimport"]

# Census country codes. "-" asks for the total for all countries (to get market share).
COUNTRIES = {"bangladesh": "5380", "china": "5700", "vietnam": "5520", "india": "5330",
             "cambodia": "5550", "indonesia": "5600", "pakistan": "5350", "sri_lanka": "5420",
             "world": "-"}
CHAPTERS = ["61", "62", "63", "64"]   # knitted apparel, woven apparel, home textiles, footwear
FIELDS = ["CTY_CODE", "I_COMMODITY", "I_COMMODITY_SDESC", "GEN_VAL_MO", "CON_VAL_MO",
          "DUT_VAL_MO", "CAL_DUT_MO", "CON_QY1_MO", "UNIT_QY1"]
PAUSE = 1.0


def census_key():
    k = os.environ.get("CENSUS_KEY")
    p = os.path.join(ROOT, ".env")
    if not k and os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.strip().startswith("CENSUS_KEY="):
                k = line.split("=", 1)[1].strip().strip('"').strip("'")
    return k


def call(base, cty, chapter, year, key):
    last = date.today().replace(day=1)
    to = f"{year}-12" if year < last.year else f"{year}-{last.month:02d}"
    q = {"get": ",".join(FIELDS), "time": f"from {year}-01 to {to}", "COMM_LVL": "HS6",
         "I_COMMODITY": f"{chapter}*", "CTY_CODE": cty}
    if key:
        q["key"] = key
    url = base + "?" + urllib.parse.urlencode(q, safe="*,-")
    req = urllib.request.Request(url, headers={"User-Agent": "trade research (pervejhosen.com)"})
    with urllib.request.urlopen(req, timeout=90) as r:
        body = r.read().decode("utf-8", "replace")
        if "missing_key" in r.geturl() or "Missing Key" in body:
            raise SystemExit("The Census API needs a key. Add CENSUS_KEY=... to .env (see the top of this script).")
        if r.status == 204 or not body.strip():
            return url, r.status, []
        try:
            return url, r.status, json.loads(body)
        except json.JSONDecodeError:
            raise ValueError("Not JSON. The reply starts: " + body[:150].replace("\n", " "))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-year", type=int, default=2017)
    ap.add_argument("--to-year", type=int, default=date.today().year)
    ap.add_argument("--countries", default=",".join(COUNTRIES))
    ap.add_argument("--chapters", default=",".join(CHAPTERS))
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    key = census_key()
    if not key:
        sys.exit("No CENSUS_KEY in .env. Get a free key at https://api.census.gov/data/key_signup.html")
    os.makedirs(OUT, exist_ok=True)

    jobs = [(c, ch, y) for c in a.countries.split(",") for ch in a.chapters.split(",")
            for y in range(a.from_year, a.to_year + 1)]
    if a.test:
        jobs = [("bangladesh", "62", date.today().year - 1)]

    log_path = os.path.join(OUT, "_log.csv")
    new = not os.path.exists(log_path)
    with open(log_path, "a", newline="", encoding="utf-8") as lf:
        w = csv.writer(lf)
        if new:
            w.writerow(["time", "country", "chapter", "year", "status", "rows", "note"])
        for c, ch, y in jobs:
            path = os.path.join(OUT, f"{c}_{ch}_{y}.json")
            if os.path.exists(path) and not a.test:
                continue
            for base in BASES:
                try:
                    url, status, data = call(base, COUNTRIES[c], ch, y, key)
                    rows = max(0, len(data) - 1)
                    if not a.test:
                        with open(path, "w", encoding="utf-8") as f:
                            json.dump({"source": url.split("&key=")[0], "retrieved": datetime.now().isoformat(timespec="seconds"),
                                       "data": data}, f)
                    w.writerow([datetime.now().isoformat(timespec="seconds"), c, ch, y, status, rows, base.rsplit("/", 1)[1]])
                    print(f"{c:11s} ch{ch} {y}  {rows:6d} rows  ({base.rsplit('/', 1)[1]})")
                    if a.test:
                        for r in data[:6]:
                            print("   ", r)
                    break
                except urllib.error.HTTPError as e:
                    msg = e.read()[:200].decode("utf-8", "replace")
                    w.writerow([datetime.now().isoformat(timespec="seconds"), c, ch, y, e.code, 0, msg])
                    print(f"{c:11s} ch{ch} {y}  HTTP {e.code} at {base.rsplit('/', 1)[1]}: {msg}")
                except (urllib.error.URLError, TimeoutError, ValueError) as e:
                    w.writerow([datetime.now().isoformat(timespec="seconds"), c, ch, y, "error", 0, str(e)[:200]])
                    print(f"{c:11s} ch{ch} {y}  ERROR {str(e)[:120]}")
                finally:
                    lf.flush()
                    time.sleep(PAUSE)
    print(f"\nFiles in {OUT}")


if __name__ == "__main__":
    sys.exit(main())
