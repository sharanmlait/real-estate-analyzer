"""Crawl one site and save the raw results to data/raw/<site>_<timestamp>.json.

    python -m crawler.run --site practice --max-pages 60 --delay 0.2
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime

from crawler.base import PoliteCrawler
from crawler.sites import SITES
from src.config import RAW_DIR


def crawl_site(site: str, max_pages: int = 60, delay: float = 3.0, base_url: str | None = None) -> tuple[list[dict], str]:
    factory = SITES[site]
    adapter = factory(base_url) if base_url else factory()
    rows = PoliteCrawler(adapter, delay=delay).crawl(max_pages=max_pages)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{site}_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    return rows, str(path)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="practice", choices=sorted(SITES))
    ap.add_argument("--max-pages", type=int, default=60)
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between requests")
    ap.add_argument("--base-url", default=None)
    a = ap.parse_args()
    rows, path = crawl_site(a.site, a.max_pages, a.delay, a.base_url)
    print(f"Saved {len(rows)} raw listings to {path}")


if __name__ == "__main__":
    main()
