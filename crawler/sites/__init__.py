"""Registry of site adapters. Add your own here."""
from crawler.sites import practice

SITES = {
    "practice": practice.make,
    # "mysite": template.make,   # after you fill in crawler/sites/template.py
}
