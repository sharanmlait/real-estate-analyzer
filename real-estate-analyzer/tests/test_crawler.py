from crawler.base import BlockedError
from crawler.sites.practice import make

HTML = """<article class="listing-card" data-id="P1">
  <h2 class="title"><a href="/listing/P1">3 BHK Apartment in Sector 62</a></h2>
  <div class="price">₹ 1.2 Cr</div><span class="bhk">3 BHK</span><span class="area">1500 sqft</span>
  <span class="status">Ready to Move</span><span class="age">2 years</span>
  <span class="locality">Sec 62</span><span class="city">Noida</span><div class="builder">B</div>
</article><a class="next" href="/listings?page=2">Next</a>"""


def test_parse_cards_and_next_link():
    rows, nxt = make("http://x").parse(HTML, "http://x/listings?page=1")
    assert len(rows) == 1
    assert rows[0]["listing_id"] == "P1" and rows[0]["price"] == "₹ 1.2 Cr"
    assert rows[0]["url"] == "http://x/listing/P1"
    assert nxt == "http://x/listings?page=2"


def test_stops_on_captcha():
    try:
        make("http://x").parse("<p>Please solve the CAPTCHA</p>", "http://x")
    except BlockedError:
        return
    raise AssertionError("expected BlockedError")
