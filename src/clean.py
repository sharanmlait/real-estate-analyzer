"""Turn raw crawled listings into analysis-ready rows.

Every decision is documented here, and `clean()` returns a report of how many
rows each rule removed so the dashboard can show it.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .config import LOCALITY_INFO

SQFT_PER_SQYD = 9.0
SQFT_PER_SQM = 10.7639

# Hard sanity bounds for Delhi NCR apartments (rupees per sq ft).
PPSF_MIN, PPSF_MAX = 1_500, 100_000

# ---------------------------------------------------------------- price

_NUM = r"(\d+(?:\.\d+)?)"


def parse_price(text) -> float:
    """'₹ 1.25 Cr' -> 12500000.0, '85 Lac' -> 8500000.0, 'On request' -> nan.

    Ranges like '1.20 - 1.35 Cr' become the midpoint.
    """
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return np.nan
    s = str(text).lower().replace("₹", "").replace("rs.", "").replace("inr", "").strip()
    if not s or "request" in s or "call" in s:
        return np.nan

    if re.search(r"\bcr(ore)?s?\b|\bcr\b", s):
        mult = 1e7
    elif re.search(r"\b(lac|lakh|lacs|lakhs|l)\b", s) or re.search(r"\d\s*l\b", s):
        mult = 1e5
    else:
        mult = 1.0

    numbers = [float(x) for x in re.findall(_NUM, s.replace(",", ""))]
    if not numbers:
        return np.nan
    value = sum(numbers[:2]) / len(numbers[:2]) if "-" in s or " to " in s else numbers[0]
    return value * mult


# ---------------------------------------------------------------- area

def parse_area(text) -> float:
    """Convert '1,450 sqft', '160 sq yd', '135 sqm' to square feet."""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return np.nan
    s = str(text).lower().replace(",", "")
    m = re.search(_NUM, s)
    if not m:
        return np.nan
    v = float(m.group(1))
    if re.search(r"sq\.?\s*y(ar)?d|gaj", s):
        return v * SQFT_PER_SQYD
    if re.search(r"sq\.?\s*m(et(er|re))?s?\b|sqm|m2", s):
        return v * SQFT_PER_SQM
    return v  # sq ft by default


# ---------------------------------------------------------------- bhk / status / age

def parse_bhk(text) -> float:
    s = str(text).lower()
    if "rk" in s or "studio" in s:
        return 1
    m = re.search(r"(\d+)", s)
    return float(m.group(1)) if m else np.nan


def normalize_status(text) -> str:
    s = str(text).lower().replace("_", " ")
    if "under" in s or "construction" in s or "new launch" in s:
        return "Under Construction"
    if "ready" in s or "resale" in s:
        return "Ready to Move"
    return "Unknown"


def parse_age(text) -> float:
    s = str(text).lower()
    if s in ("new", "", "nan", "none") or "new" in s:
        return 0.0
    m = re.search(r"(\d+)", s)
    return float(m.group(1)) if m else np.nan


# ---------------------------------------------------------------- locality

_ALIASES = {
    "gcer": "Golf Course Extension Road",
    "golf course ext rd": "Golf Course Extension Road",
    "greater noida west": "Noida Extension",
    "noida extn": "Noida Extension",
    "dwarka expy": "Dwarka Expressway",
    "dwarka exp way": "Dwarka Expressway",
    "dlf ph 5": "DLF Phase 5",
    "dlf phase v": "DLF Phase 5",
    "rne": "Raj Nagar Extension",
    "rajnagar extn": "Raj Nagar Extension",
}
_CANON = {k.lower(): k for k in LOCALITY_INFO}


def normalize_locality(text) -> str:
    """'Sec-62', 'SECTOR 62', 'Sector 62 Noida' -> 'Sector 62'."""
    s = str(text).strip().lower()
    s = re.sub(r"[.\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\b(sec|sect|sector)\s*(\d+)", r"sector \2", s)
    s = re.sub(r"\s+(noida|gurgaon|gurugram|delhi|ghaziabad)$", "", s)
    if s in _ALIASES:
        return _ALIASES[s]
    if s in _CANON:
        return _CANON[s]
    return s.title()  # unknown locality: keep it, title-cased


def normalize_city(text) -> str:
    s = str(text).strip().lower()
    return {"gurgaon": "Gurugram", "new delhi": "Delhi"}.get(s, s.title())


# ---------------------------------------------------------------- pipeline

def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Return (clean dataframe, report of rows removed per rule)."""
    report = {"raw_rows": len(raw)}
    df = raw.copy()

    # Optional columns get defaults, so a public dataset with fewer columns still loads.
    required = {"price", "area", "bhk", "locality", "city"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Raw data is missing required columns: {sorted(missing)}")
    defaults = {"title": None, "url": None, "builder": "", "status": "", "age": "",
                "source": "unknown", "scraped_at": pd.Timestamp.now().floor("s")}
    for col, val in defaults.items():
        if col not in df:
            df[col] = val
    if "listing_id" not in df:
        df["listing_id"] = [f"row-{i}" for i in range(len(df))]
    df["title"] = df["title"].fillna(df["bhk"].astype(str) + " in " + df["locality"].astype(str))

    df["price"] = df["price"].map(parse_price)
    df["area_sqft"] = df["area"].map(parse_area).round(0)
    df["bhk"] = df["bhk"].map(parse_bhk)
    df["locality"] = df["locality"].map(normalize_locality)
    df["city"] = df["city"].map(normalize_city)
    df["status"] = df["status"].map(normalize_status)
    df["age_years"] = df["age"].map(parse_age) if "age" in df else np.nan
    df["builder"] = df["builder"].fillna("").replace("", "Unknown")
    df["scraped_at"] = pd.to_datetime(df["scraped_at"])
    df["scraped_date"] = df["scraped_at"].dt.strftime("%Y-%m-%d")

    # Rule 1: drop rows missing the fields every analysis needs.
    before = len(df)
    df = df.dropna(subset=["price", "area_sqft", "bhk"])
    report["dropped_missing_price_area_bhk"] = before - len(df)

    df["price_per_sqft"] = (df["price"] / df["area_sqft"]).round(0)

    # Rule 2: hard sanity bounds catch typos like ₹1 or an extra two zeros.
    before = len(df)
    df = df[df["price_per_sqft"].between(PPSF_MIN, PPSF_MAX)]
    report["dropped_out_of_bounds"] = before - len(df)

    # Rule 3: per-locality IQR filter (1.5 x IQR) on price per sq ft, per crawl date.
    before = len(df)
    g = df.groupby(["scraped_date", "locality"])["price_per_sqft"]
    q1, q3 = g.transform(lambda s: s.quantile(0.25)), g.transform(lambda s: s.quantile(0.75))
    iqr = q3 - q1
    df = df[(df["price_per_sqft"] >= q1 - 1.5 * iqr) & (df["price_per_sqft"] <= q3 + 1.5 * iqr)]
    report["dropped_iqr_outliers"] = before - len(df)

    # Rule 4: the same flat posted twice in one crawl (same locality, BHK,
    # area within 1%, price within 1%) is kept once.
    before = len(df)
    df = df.assign(_a=(df["area_sqft"] / 15).round(), _p=(df["price"] / 2e5).round())
    df = df.drop_duplicates(subset=["scraped_date", "locality", "bhk", "_a", "_p"]).drop(columns=["_a", "_p"])
    report["dropped_duplicates"] = before - len(df)

    # Rule 5: one row per listing per crawl timestamp.
    before = len(df)
    df = df.drop_duplicates(subset=["listing_id", "scraped_at"])
    report["dropped_same_listing_twice"] = before - len(df)

    df["scraped_at"] = df["scraped_at"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    cols = ["listing_id", "title", "locality", "city", "bhk", "area_sqft", "price",
            "price_per_sqft", "builder", "status", "age_years", "url", "source",
            "scraped_at", "scraped_date"]
    df = df[cols].reset_index(drop=True)
    report["clean_rows"] = len(df)
    return df, report
