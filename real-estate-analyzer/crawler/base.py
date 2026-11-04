"""A polite, reusable crawler.

Each site gets a small adapter (see crawler/sites/) that only knows URLs and
CSS selectors, so when a site changes its layout you edit one file.

Politeness built in:
  * checks robots.txt and refuses disallowed paths
  * honours Crawl-delay, otherwise waits `delay` seconds (+ jitter) per request
  * identifies itself with a custom User-Agent
  * retries 429/5xx with exponential backoff, never hammers
  * stops on CAPTCHA / block pages instead of trying to bypass them
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("crawler")

USER_AGENT = "RealEstateAnalyzer-StudentProject/1.0 (+https://github.com/sharanmlait/real-estate-analyzer)"


class BlockedError(RuntimeError):
    """Raised when a site shows a CAPTCHA or blocks us. We stop, we don't bypass."""


@dataclass
class SiteAdapter:
    """Everything site-specific lives here."""
    name: str
    base_url: str
    start_path: str
    card: str                      # CSS selector for one listing card
    fields: dict[str, str]         # output field -> CSS selector inside the card
    next_page: str | None = None   # CSS selector for the "next" link
    id_attr: str | None = None     # card attribute holding a stable listing id
    link: str | None = "a"         # selector for the detail link inside the card
    default_city: str | None = None
    extra: dict = field(default_factory=dict)

    def parse(self, html: str, page_url: str) -> tuple[list[dict], str | None]:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True).lower()
        if "captcha" in text or "access denied" in text or "unusual traffic" in text:
            raise BlockedError(f"{self.name}: block/CAPTCHA page at {page_url}")
        rows = []
        for c in soup.select(self.card):
            row = {}
            for key, sel in self.fields.items():
                el = c.select_one(sel)
                row[key] = el.get_text(" ", strip=True) if el else None
            a = c.select_one(self.link) if self.link else None
            row["url"] = urljoin(page_url, a["href"]) if a and a.has_attr("href") else page_url
            row["listing_id"] = c.get(self.id_attr) if self.id_attr else None
            row["listing_id"] = row["listing_id"] or row["url"]
            if not row.get("city") and self.default_city:
                row["city"] = self.default_city
            rows.append(row)
        nxt = None
        if self.next_page:
            a = soup.select_one(self.next_page)
            if a and a.has_attr("href"):
                nxt = urljoin(page_url, a["href"])
        return rows, nxt


class PoliteCrawler:
    def __init__(self, site: SiteAdapter, delay: float = 3.0, timeout: float = 15.0):
        self.site = site
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-IN,en;q=0.9"})
        retry = Retry(total=4, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["GET"], respect_retry_after_header=True)
        self.session.mount("http://", HTTPAdapter(max_retries=retry))
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.robots = self._load_robots()

    def _load_robots(self) -> RobotFileParser:
        rp = RobotFileParser()
        robots_url = urljoin(self.site.base_url, "/robots.txt")
        try:
            r = self.session.get(robots_url, timeout=self.timeout)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except requests.RequestException:
            log.warning("Could not read %s; treating everything as allowed", robots_url)
            rp.parse([])
        cd = rp.crawl_delay(USER_AGENT)
        if cd:
            self.delay = max(self.delay, float(cd))
        return rp

    def allowed(self, url: str) -> bool:
        return self.robots.can_fetch(USER_AGENT, url)

    def fetch(self, url: str) -> str:
        if not self.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        r = self.session.get(url, timeout=self.timeout)
        if r.status_code in (401, 403):
            raise BlockedError(f"{self.site.name}: HTTP {r.status_code} at {url}")
        r.raise_for_status()
        return r.text

    def crawl(self, max_pages: int = 50) -> list[dict]:
        url = urljoin(self.site.base_url, self.site.start_path)
        scraped_at = datetime.now().replace(microsecond=0).isoformat()
        seen, out = set(), []
        for page in range(1, max_pages + 1):
            if url in seen:
                break
            seen.add(url)
            try:
                html = self.fetch(url)
                rows, nxt = self.site.parse(html, url)
            except BlockedError as e:
                log.error("%s - stopping crawl. Slow down or switch to a permitted source.", e)
                break
            except (requests.RequestException, PermissionError) as e:
                log.error("Page %d failed: %s", page, e)
                break
            for r in rows:
                r["scraped_at"] = scraped_at
                r["source"] = self.site.name
            out.extend(rows)
            log.info("page %d: %d listings (total %d)", page, len(rows), len(out))
            if not nxt or not rows:
                break
            url = nxt
            time.sleep(self.delay + random.uniform(0, self.delay * 0.3))
        return out

