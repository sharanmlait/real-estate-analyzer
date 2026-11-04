# Delhi NCR Real Estate Price Analyzer

Crawls property listings, cleans them, stores every crawl in SQLite, analyses
price per sq ft across 18 Delhi NCR localities, tracks price changes over time,
and predicts a fair price, all behind a Streamlit dashboard.

```
practice site / permitted site ──► crawler ──► data/raw/*.json
                                                   │
                                     clean (src/clean.py)  ── report of rows dropped per rule
                                                   │
                                SQLite: listings + crawl_runs (one row per listing per crawl)
                                                   │
                     analysis (src/analysis.py) ── model (src/model.py)
                                                   │
                                    Streamlit dashboard (app/)
```

> **About the data.** Out of the box the project runs on **synthetic** listings
> (`src/sample_data.py`) served by a local practice website. Prices come from
> formulas plus noise, so the numbers below show the pipeline working, **not**
> the real Delhi NCR market. Builder names are fictional. Point the crawler at
> a source you are allowed to use to get real data.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python pipeline.py seed --reset        # 16 weeks of synthetic history (~19k rows)
python pipeline.py train               # trains and saves the price model
streamlit run app/streamlit_app.py     # http://localhost:8501
```

### Crawl the live practice site

```bash
# terminal 1: a small local listings website (paginated HTML, robots.txt, messy data)
python -m mock_site.server --port 8765

# terminal 2: crawl -> clean -> store, then retrain
python pipeline.py crawl --site practice --delay 1
python pipeline.py train
```

### Real-time demo mode

The practice site can re-price its listings every few minutes, and `watch`
re-crawls on a timer. Refresh the dashboard to see new crawls arrive.

```bash
python -m mock_site.server --tick 5           # prices update every 5 minutes
python pipeline.py watch --every 5 --delay 1 --retrain
```

## What's inside

| Path | What it does |
|---|---|
| `crawler/base.py` | Polite crawler: robots.txt check, Crawl-delay, custom User-Agent, retries with backoff, pagination, stops on CAPTCHA/403 instead of bypassing |
| `crawler/sites/` | One small adapter per site (URLs + CSS selectors). `template.py` is the starting point for a real site |
| `mock_site/server.py` | Local practice listings site (stdlib only) with an optional JSON API (`--js`) |
| `src/clean.py` | Parses `₹1.25 Cr` / `85 Lac` / `₹ 1,17,80,000` / ranges, sq yd and sq m to sq ft, locality spellings, dedupe, outliers |
| `src/db.py` | SQLite schema; unique on (source, listing_id, scraped_at) so re-runs never double-insert |
| `src/analysis.py` | Locality, BHK, builder and status comparisons, weekly trends, like-for-like price change, top deals, plain-English findings |
| `src/model.py` | Ridge regression vs Random Forest on log(price); keeps the lower-MAPE model and gives an 80% range from the trees |
| `app/streamlit_app.py` | Dashboard: filters, KPIs, 7 tabs (overview, trends, map, top deals, builders, predictor, pipeline log) |
| `pipeline.py` | `seed`, `crawl`, `ingest`, `train`, `watch`, `status` |
| `.github/workflows/crawl.yml` | Daily crawl + retrain on GitHub Actions, commits the updated database |
| `tests/` | 35 pytest tests for parsing, cleaning, crawler parsing and analysis |

## Cleaning decisions

Each rule is counted per run and shown on the dashboard's Pipeline tab.

1. **Prices** are converted to rupees: Cr = 10⁷, Lac/Lakh/L = 10⁵, Indian comma
   format parsed directly, ranges take the midpoint. "Price on request" becomes missing.
2. **Area** is standardised to sq ft (1 sq yd = 9 sq ft, 1 sq m = 10.7639 sq ft).
3. **Locality names** are normalised (`Sec-62`, `SECTOR 62`, `Sector 62 Noida` → `Sector 62`)
   and known aliases mapped (`GCER` → Golf Course Extension Road, `Greater Noida West` → Noida Extension).
4. **Missing** price, area or BHK: the row is dropped (they are needed for every metric).
5. **Hard bounds**: ₹1,500 to ₹1,00,000 per sq ft. Catches typos like ₹1 or two extra zeros.
6. **IQR filter**: per locality and crawl date, outside 1.5 × IQR of price per sq ft is dropped.
7. **Duplicates**: same crawl date, locality, BHK, area within ~1% and price within ₹2 L is one flat.

## Analysis notes

**Price change uses the same flats.** Comparing this week's median with the
median four weeks ago mostly measures which flats happen to be listed. The
dashboard instead compares each listing with its own earlier asking price and
takes the median per locality (a repeat-sales style index). On the synthetic
data this recovers the trends built into the generator; the naive median did not.

## Findings (synthetic data, for illustration)

From the bundled demo database (16 weeks of seeded history plus one practice-site crawl):

- DLF Phase 5 is the most expensive locality at about ₹21,900/sq ft; Raj Nagar Extension is the cheapest at about ₹5,100 (4.3x).
- For 3 BHK units in Gurugram, Sector 85 is about 57% cheaper per sq ft than DLF Phase 5.
- Over 4 weeks, asking prices for the same flats rose most on Dwarka Expressway (+2.5%) and least in Mayur Vihar (−0.3%).
- Under-construction flats are only ~2% cheaper per sq ft than ready-to-move ones, because the ready-to-move stock is older.

Model on the demo data (test set, 536 listings):

| Model | MAE | MAPE | R² |
|---|---|---|---|
| Ridge regression | ₹15.3 L | 7.0% | 0.963 |
| Random Forest | ₹14.3 L | 6.4% | 0.961 |

These scores are high because the generator is close to log-linear. Expect
lower scores on real listings, which is the honest number to put on a resume.

## Using real data

**Option A: a site you are allowed to crawl.** Copy `crawler/sites/template.py`,
fill in the selectors, register it in `crawler/sites/__init__.py`, add its
localities' coordinates to `src/config.py`, then `python pipeline.py crawl --site mysite`.
Read the site's terms and robots.txt first. Many big property portals forbid
scraping; state RERA portals and public datasets are safer.

**Option B: a public dataset (e.g. Kaggle).** Rename its columns to at least
`price, area, bhk, locality, city` (optional: `builder, status, age, title, url,
listing_id, scraped_at`), then:

```bash
python pipeline.py ingest data/raw/kaggle_ncr.csv --source kaggle
python pipeline.py train
```

## Deploy

- **Dashboard**: push to GitHub, then deploy `app/streamlit_app.py` on Streamlit Community Cloud. Commit `data/realestate.db` and `models/` so the hosted app has data.
- **Scheduler**: the included GitHub Actions workflow runs daily at 06:00 IST. Or locally with cron:
  `0 6 * * * cd /path/to/real-estate-analyzer && .venv/bin/python pipeline.py crawl --site mysite && .venv/bin/python pipeline.py train`

## Tests

```bash
pytest -q
```

## Resume line (once you have real data)

> Built a real estate price analyzer for Delhi NCR: a polite Python crawler (robots.txt, retries, pagination), a cleaning pipeline for messy Indian price and area formats, SQLite price history, a repeat-listing price index, and a Streamlit dashboard with maps and a Random Forest fair-price model (MAPE x%).

Fill in the numbers from your real-data run.
