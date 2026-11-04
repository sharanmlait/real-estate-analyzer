import pandas as pd

from src import analysis as A


def _df():
    rows = []
    # 6 flats in each locality, seen in week 1 and week 5. Locality A rises 10%, B is flat.
    for loc, rise in (("A", 1.10), ("B", 1.00)):
        for i in range(6):
            for date, mult in (("2026-09-01", 1.0), ("2026-09-29", rise)):
                ppsf = 10000 + i * 100
                rows.append({"listing_id": f"{loc}{i}", "title": "t", "url": "/x", "locality": loc, "city": "X", "bhk": 2,
                             "area_sqft": 1000, "price": ppsf * mult * 1000, "price_per_sqft": ppsf * mult,
                             "builder": "B", "status": "Ready to Move", "source": "t",
                             "scraped_date": date, "scraped_at": date + "T06:00:00"})
    # a new, expensive flat appears only in the last week; it must not distort B's change
    rows.append(dict(rows[-1], listing_id="B-new", price_per_sqft=30000, price=3e7))
    return pd.DataFrame(rows)


def test_price_movers_is_like_for_like():
    m = A.price_movers(_df()).set_index("locality")["change_pct"]
    assert m["A"] == 10.0 and m["B"] == 0.0


def test_latest_keeps_only_last_crawl_date():
    assert set(A.latest(_df())["scraped_date"]) == {"2026-09-29"}


def test_top_deals_flags_cheap_listing():
    d = _df()
    d = d[d.scraped_date == "2026-09-29"].copy()
    d.loc[d.listing_id == "A0", "price_per_sqft"] = 7000
    deals = A.top_deals(d, min_discount=0.1)
    assert "A" in set(deals["locality"])
