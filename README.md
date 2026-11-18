# Thread Count

Bangladesh garments in the US market, and what the 2025 and 2026 tariffs changed. An independent analysis by
Pervej Hosen using public US Census Bureau trade data.

- Case study: https://pervejhosen.com/projects/thread-count/
- Live report (Power BI): https://app.powerbi.com/view?r=eyJrIjoiYzY2YWEzNzYtNDFmOC00OTgwLWE5ZjYtZmM1OGFmZjM1MmI4IiwidCI6IjIyOTM4MjRkLWE0YjQtNDNmMi1hM2ZlLWU0Mjc2YzcxNjY2NCIsImMiOjEwfQ%3D%3D

## What it found (January to September of each year, HS chapters 61 and 62)

- Bangladesh supplied **10.3%** of US garment imports in 2026, up from 8.7% in 2024 and 6.2% in 2017.
- China's share fell **9.3 points** in two years; Vietnam gained 3.6, Cambodia 2.0, Bangladesh 1.6.
- Duty paid on Bangladesh garments rose from about **17%** to **36%** (October 2025 to January 2026) and has been about **26%** since March 2026.
- Bangladesh pays less than most competitors mostly because **71%** of what it ships is cotton, which carries a lower normal US duty.
- Five products are **52%** of Bangladesh's US garment value.
- 2027 outlook, with today's tariffs: **$7.2bn to $8.4bn**, depending on Bangladesh's share.

## What is here

| Folder | What |
|---|---|
| `tools/` | `collect_us_imports.py` downloads the data from the Census API; `build_trade.py` builds the DuckDB tables in `01_data/processed/` |
| `01_data/reference/tariff_events.csv` | 21 dated US tariff actions, each with its source |
| `03_analysis/` | three notebooks (data profile and share; tariff, exposure and seasonality; forecast) and the scripts that build them |
| `05_review/` | `verify.py` recomputes 39 headline numbers straight from the raw files, and its report |
| `08_data_pack/` | country by month (value, share, tariff) and tariff by product and year, as CSV |

The Power BI report and its custom visual are not in this repository.

## Run it

1. Get a free Census API key at https://api.census.gov/data/key_signup.html and put `CENSUS_KEY=your_key` in a `.env` file here.
2. `pip install -r requirements.txt`
3. `python tools/collect_us_imports.py` (about 360 files to `01_data/raw/`), then `python tools/build_trade.py`
4. `python 03_analysis/build_profile_nb.py` and the other two builders run the notebooks; `python 05_review/verify.py` checks the numbers.

## Definitions and limits

- Value is general imports at the US border, before duty. Share is a country's value over all US garment imports.
- Duty paid is calculated duty over the value of goods entered for consumption: the rate actually collected, not a headline rate.
- It shows what the US imported, not what Bangladesh exported, and not prices or profits. Refunds of the tariffs struck down in February 2026 are not reflected.
- OTEXA counts a wider set of garments, so its totals run a little higher; growth rates match.

## Corrections

If a number looks wrong, open an issue here or get in touch through https://pervejhosen.com. Code under the MIT licence.
