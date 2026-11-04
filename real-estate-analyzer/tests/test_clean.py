import math

import pandas as pd
import pytest

from src.clean import clean, normalize_locality, parse_area, parse_bhk, parse_price, normalize_status


@pytest.mark.parametrize("text,expected", [
    ("₹ 1.25 Cr", 12_500_000),
    ("₹1.25 Crore", 12_500_000),
    ("85 Lac", 8_500_000),
    ("92.5 Lakh", 9_250_000),
    ("₹74L", 7_400_000),
    ("₹ 1,17,80,000", 11_780_000),
    ("₹ 1.20 - 1.40 Cr", 13_000_000),
])
def test_parse_price(text, expected):
    assert parse_price(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["Price on Request", "On request", "Call for price", None, ""])
def test_parse_price_missing(text):
    assert math.isnan(parse_price(text))


@pytest.mark.parametrize("text,expected", [
    ("1450 sq.ft", 1450), ("1,450 sqft", 1450), ("1450 Sq. Ft.", 1450),
    ("160 sq yd", 1440), ("135 sq m", 135 * 10.7639), ("135 sqm", 135 * 10.7639),
])
def test_parse_area(text, expected):
    assert parse_area(text) == pytest.approx(expected)


@pytest.mark.parametrize("text,expected", [
    ("Sec 62", "Sector 62"), ("Sector-62", "Sector 62"), ("SECTOR 75", "Sector 75"),
    ("Sec. 75", "Sector 75"), ("Sector-150 Noida", "Sector 150"), ("GCER", "Golf Course Extension Road"),
    ("Greater Noida West", "Noida Extension"), ("DLF Ph-5", "DLF Phase 5"), ("Some New Place", "Some New Place"),
])
def test_normalize_locality(text, expected):
    assert normalize_locality(text) == expected


def test_bhk_and_status():
    assert parse_bhk("3BHK") == 3 and parse_bhk("1 RK") == 1
    assert normalize_status("UNDER_CONSTRUCTION") == "Under Construction"
    assert normalize_status("Ready to Move") == "Ready to Move"


def _row(i, price="₹ 1.20 Cr", area="1500 sqft", loc="Sector 62"):
    return {"listing_id": f"L{i}", "title": "t", "price": price, "area": area, "bhk": "3 BHK",
            "locality": loc, "city": "Noida", "builder": "B", "status": "Ready to Move",
            "age": "2 years", "url": "/x", "source": "test", "scraped_at": "2026-10-01T06:00:00"}


def test_clean_drops_bad_rows_and_duplicates():
    rows = [_row(i, price=f"₹ {1.10 + i * 0.02:.2f} Cr") for i in range(10)]
    rows.append(_row(99, price="On request"))           # missing price
    rows.append(_row(98, price="₹ 1"))                  # typo outlier
    rows.append(dict(rows[0], listing_id="L0-repost"))  # same flat posted twice
    df, rep = clean(pd.DataFrame(rows))
    assert rep["dropped_missing_price_area_bhk"] == 1
    assert rep["dropped_out_of_bounds"] == 1
    assert rep["dropped_duplicates"] == 1
    assert len(df) == 10
    assert (df["price_per_sqft"] == (df["price"] / df["area_sqft"]).round()).all()


def test_clean_accepts_minimal_dataset():
    raw = pd.DataFrame({"price": ["85 Lac"], "area": ["1000 sqft"], "bhk": ["2 BHK"],
                        "locality": ["Sec 62"], "city": ["noida"]})
    df, _ = clean(raw)
    assert df.loc[0, "locality"] == "Sector 62" and df.loc[0, "city"] == "Noida"
