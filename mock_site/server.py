"""A tiny local listings website for building and testing the crawler.

It serves synthetic Delhi NCR listings as paginated HTML, the way a small
property portal would. Prices drift with time, so every crawl sees fresh
numbers. Run it with:

    python -m mock_site.server --port 8765

Options:
    --tick N   minutes between price updates (default 1440 = once a day).
               Use --tick 5 with `pipeline.py watch` for a live demo.
    --js       also expose /api/listings (JSON), like many JS-heavy sites do.
"""
from __future__ import annotations

import argparse
import html
import json
import math
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from src.sample_data import build_properties, snapshot

PER_PAGE = 24
PROPS = build_properties()
TICK_MINUTES = 1440
_cache: dict[str, list[dict]] = {}


def current_listings() -> list[dict]:
    now = datetime.now()
    minutes = (now.hour * 60 + now.minute) // TICK_MINUTES * TICK_MINUTES
    tick = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)
    key = tick.isoformat()
    if key not in _cache:
        _cache.clear()
        _cache[key] = snapshot(PROPS, tick)
    return _cache[key]


def card(row: dict) -> str:
    e = html.escape
    return f"""
    <article class="listing-card" data-id="{e(row['listing_id'])}">
      <h2 class="title"><a href="{e(row['url'])}">{e(row['title'])}</a></h2>
      <div class="price">{e(row['price'])}</div>
      <div class="meta">
        <span class="bhk">{e(row['bhk'])}</span> &middot;
        <span class="area">{e(row['area'])}</span> &middot;
        <span class="status">{e(row['status'])}</span> &middot;
        <span class="age">{e(row['age'])}</span>
      </div>
      <div class="location"><span class="locality">{e(row['locality'])}</span>,
        <span class="city">{e(row['city'])}</span></div>
      <div class="builder">{e(row['builder'])}</div>
    </article>"""


def page_html(page: int) -> str:
    rows = current_listings()
    pages = max(1, math.ceil(len(rows) / PER_PAGE))
    chunk = rows[(page - 1) * PER_PAGE: page * PER_PAGE]
    nxt = f'<a class="next" rel="next" href="/listings?page={page + 1}">Next &rarr;</a>' if page < pages else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>NCR Homes (practice site) - page {page}</title>
<style>body{{font-family:system-ui;max-width:900px;margin:auto;padding:16px}}
.listing-card{{border:1px solid #ddd;border-radius:8px;padding:12px;margin:10px 0}}
.price{{font-weight:700;font-size:1.2em}}</style></head><body>
<p><strong>Practice site.</strong> Synthetic listings for crawler testing, not real properties.</p>
<p class="count">{len(rows)} listings &middot; page {page} of {pages}</p>
{''.join(card(r) for r in chunk)}
<nav class="pagination">{nxt}</nav>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "NCRHomesPractice/1.0"

    def _send(self, body: str, ctype="text/html; charset=utf-8", code=200):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        q = parse_qs(url.query)
        if url.path == "/robots.txt":
            return self._send("User-agent: *\nAllow: /\nCrawl-delay: 1\n", "text/plain")
        if url.path in ("/", "/listings"):
            page = max(1, int(q.get("page", ["1"])[0]))
            return self._send(page_html(page))
        if url.path == "/api/listings" and self.server.enable_json:
            page = max(1, int(q.get("page", ["1"])[0]))
            rows = current_listings()
            chunk = rows[(page - 1) * PER_PAGE: page * PER_PAGE]
            return self._send(json.dumps({"page": page, "total": len(rows), "results": chunk}), "application/json")
        return self._send("Not found", "text/plain", 404)

    def log_message(self, *args):  # keep the console quiet
        pass


def main():
    global TICK_MINUTES
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--tick", type=int, default=1440)
    ap.add_argument("--js", action="store_true")
    a = ap.parse_args()
    TICK_MINUTES = max(1, a.tick)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    srv.enable_json = a.js
    print(f"Practice listings site on http://127.0.0.1:{a.port}/listings (prices update every {TICK_MINUTES} min)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
