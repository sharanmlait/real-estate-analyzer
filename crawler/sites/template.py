"""Template for a real site. Copy this file, then fill in the selectors.

Before you crawl any real site:
  1. Read its terms of service. Many big property portals forbid scraping.
  2. Read https://<site>/robots.txt. The crawler enforces it, but check yourself.
  3. Prefer an official API, a public registry (state RERA portals) or a
     public dataset when one exists.
  4. Keep the delay at 3s or more and crawl only what you need.
  5. If you hit a CAPTCHA or a 403, stop. Do not try to bypass it.

How to find selectors: open a results page, right-click a listing -> Inspect,
and note the class names around the price, area and locality. If the HTML has
no listings in it (the page fills itself with JavaScript), open DevTools ->
Network -> Fetch/XHR, reload, and look for a JSON endpoint instead; that is
usually easier and lighter than a headless browser.
"""
from crawler.base import SiteAdapter


def make() -> SiteAdapter:
    return SiteAdapter(
        name="mysite",                          # becomes the `source` column
        base_url="https://example.com",         # site you have permission to crawl
        start_path="/delhi-ncr/apartments?page=1",
        card=".listing-card",                   # one result card
        id_attr="data-listing-id",              # stable id attribute, if any
        link="a",
        next_page="a[rel=next]",
        default_city=None,                      # set if cards don't show the city
        fields={
            "title": ".title",
            "price": ".price",
            "area": ".area",
            "bhk": ".bhk",
            "locality": ".locality",
            "city": ".city",
            "builder": ".builder",
            "status": ".status",
            "age": ".age",
        },
    )
