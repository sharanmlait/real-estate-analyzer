"""Adapter for the local practice site in mock_site/server.py."""
from crawler.base import SiteAdapter


def make(base_url: str = "http://127.0.0.1:8765") -> SiteAdapter:
    return SiteAdapter(
        name="practice",
        base_url=base_url,
        start_path="/listings?page=1",
        card="article.listing-card",
        id_attr="data-id",
        link="h2.title a",
        next_page="a.next",
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
