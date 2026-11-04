"""One entry point for the whole data pipeline.

    python pipeline.py seed               # load 16 weeks of SYNTHETIC history (demo)
    python pipeline.py crawl              # crawl -> clean -> store (default: practice site)
    python pipeline.py ingest FILE.json   # clean + store a raw file (e.g. a public dataset)
    python pipeline.py train              # train and save the price model
    python pipeline.py watch --every 5    # crawl every 5 min, retrain each run (live demo)
    python pipeline.py status             # what is in the database
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import pandas as pd

from src import db
from src.clean import clean
from src.config import DB_PATH, RAW_DIR

log = logging.getLogger("pipeline")


def store(raw_rows: list[dict], source: str) -> dict:
    if not raw_rows:
        log.warning("No raw rows from %s; nothing stored", source)
        return {"raw_rows": 0, "clean_rows": 0, "inserted": 0}
    df, report = clean(pd.DataFrame(raw_rows))
    inserted = db.insert_listings(df)
    db.log_run(source, report, inserted)
    report["inserted"] = inserted
    log.info("%s: %s", source, report)
    return report


def cmd_seed(a):
    from src.sample_data import build_properties, history
    if a.reset and DB_PATH.exists():
        DB_PATH.unlink()
    rows = history(build_properties(), weeks=a.weeks)
    store(rows, "sample")


def cmd_crawl(a):
    from crawler.run import crawl_site
    rows, path = crawl_site(a.site, a.max_pages, a.delay, a.base_url)
    log.info("raw saved to %s", path)
    store(rows, a.site)


def cmd_ingest(a):
    p = Path(a.file)
    rows = pd.read_csv(p).to_dict("records") if p.suffix == ".csv" else json.loads(p.read_text())
    store(rows, a.source or p.stem.split("_")[0])


def cmd_train(_a):
    from src.model import train
    m = train(db.load_listings())
    print(json.dumps(m, indent=2))


def cmd_watch(a):
    while True:
        try:
            cmd_crawl(a)
            if a.retrain:
                cmd_train(a)
        except Exception:  # keep the loop alive; the next tick may succeed
            log.exception("run failed")
        log.info("sleeping %d min", a.every)
        time.sleep(a.every * 60)


def cmd_status(_a):
    df = db.load_listings()
    if df.empty:
        print("Database is empty. Run: python pipeline.py seed   (or crawl)")
        return
    print(df.groupby(["source", "scraped_date"]).size().rename("rows").tail(20).to_string())
    print(f"\n{len(df):,} rows, {df['listing_id'].nunique():,} listings, "
          f"{df['locality'].nunique()} localities")
    print(db.load_runs().head(5)[["started_at", "source", "raw_rows", "clean_rows", "inserted"]].to_string(index=False))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("seed"); s.add_argument("--weeks", type=int, default=16)
    s.add_argument("--reset", action="store_true", help="delete the database first")
    s.set_defaults(fn=cmd_seed)

    for name, fn in (("crawl", cmd_crawl), ("watch", cmd_watch)):
        c = sub.add_parser(name)
        c.add_argument("--site", default="practice")
        c.add_argument("--max-pages", type=int, default=80)
        c.add_argument("--delay", type=float, default=3.0)
        c.add_argument("--base-url", default=None)
        if name == "watch":
            c.add_argument("--every", type=int, default=60, help="minutes between crawls")
            c.add_argument("--retrain", action="store_true")
        c.set_defaults(fn=fn)

    i = sub.add_parser("ingest"); i.add_argument("file"); i.add_argument("--source")
    i.set_defaults(fn=cmd_ingest)
    sub.add_parser("train").set_defaults(fn=cmd_train)
    sub.add_parser("status").set_defaults(fn=cmd_status)

    a = ap.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    a.fn(a)


if __name__ == "__main__":
    main()
