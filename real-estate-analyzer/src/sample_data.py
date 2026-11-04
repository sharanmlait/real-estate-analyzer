"""Synthetic Delhi NCR listings for demos and for the local mock site.

THIS IS NOT REAL MARKET DATA. Prices come from simple formulas plus noise, so
the dashboard has something to show before you crawl a permitted source.

The output is deliberately messy (mixed price/area formats, locality spelling
variants, reposted duplicates, typo outliers, "Price on request") so the
cleaning step has real work to do.
"""
from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, timedelta

from .config import BUILDERS, LOCALITIES, STATUSES

EPOCH = date(2026, 7, 1)  # day 0 of the price curves
SOURCE_NAME = "sample"

_LOC = {name: (city, base, trend) for name, city, _la, _lo, base, trend in LOCALITIES}

# Spelling variants a real portal might show for the same place.
_VARIANTS = {
    "Sector 65": ["Sector 65", "Sec 65", "Sector-65", "sector 65"],
    "Sector 85": ["Sector 85", "Sec-85", "Sector 85 Gurgaon"],
    "Sector 150": ["Sector 150", "Sec 150", "Sector-150 Noida"],
    "Sector 62": ["Sector 62", "Sec 62", "Sector-62"],
    "Sector 75": ["Sector 75", "Sec. 75", "SECTOR 75"],
    "Sector 137": ["Sector 137", "Sec 137"],
    "Golf Course Extension Road": ["Golf Course Extension Road", "Golf Course Ext Rd", "GCER"],
    "Noida Extension": ["Noida Extension", "Greater Noida West", "Noida Extn"],
    "Dwarka Expressway": ["Dwarka Expressway", "Dwarka Expy", "Dwarka Exp. Way"],
    "DLF Phase 5": ["DLF Phase 5", "DLF Ph-5", "DLF Phase V"],
    "Raj Nagar Extension": ["Raj Nagar Extension", "RNE", "Rajnagar Extn"],
}


def _rng(*parts) -> random.Random:
    seed = int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)
    return random.Random(seed)


CYCLE_DAYS = 200  # listings come back on a cycle, so the site never runs dry


def build_properties(n: int = 2600, seed: int = 42) -> list[dict]:
    """Create the underlying 'true' properties with a recurring active window each."""
    r = random.Random(seed)
    props = []
    names = [l[0] for l in LOCALITIES]
    weights = [3, 4, 4, 4, 5, 3, 4, 3, 3, 3, 5, 3, 2, 3, 2, 4, 3, 2]
    for i in range(n):
        loc = r.choices(names, weights)[0]
        bhk = r.choices([1, 2, 3, 4, 5], [8, 30, 38, 18, 6])[0]
        area = int(r.gauss(450 + 520 * bhk, 120 + 40 * bhk))
        area = max(380, area)
        builder = r.choice(list(BUILDERS))
        status = r.choices(STATUSES, [65, 35])[0]
        age = 0 if status == "Under Construction" else r.choice([1, 2, 3, 5, 8, 12, 18])
        start = r.randint(0, CYCLE_DAYS - 1)
        props.append({
            "pid": f"P{i:05d}",
            "locality": loc,
            "bhk": bhk,
            "area_sqft": area,
            "builder": builder,
            "status": status,
            "age_years": age,
            "noise": r.lognormvariate(0, 0.07),
            "start_day": start,
            "duration": r.randint(35, 150),
            "duplicate": r.random() < 0.04,  # reposted by a second agent
        })
    return props


def true_price(p: dict, day: float) -> float:
    city, base, trend = _LOC[p["locality"]]
    ppsf = base * (1 + trend) ** (day / 7)
    ppsf *= BUILDERS[p["builder"]]
    ppsf *= 0.90 if p["status"] == "Under Construction" else 1.0
    ppsf *= 1 - min(p["age_years"], 20) * 0.008
    ppsf *= 1 + 0.05 * (p["bhk"] >= 4)  # premium for large units
    ppsf *= p["noise"]
    return ppsf * p["area_sqft"]


# ---------- messy formatting ----------

def _fmt_price(rupees: float, r: random.Random) -> str:
    if r.random() < 0.02:
        return r.choice(["Price on Request", "On request", "Call for price"])
    cr, lac = rupees / 1e7, rupees / 1e5
    style = r.random()
    if rupees >= 1e7 and style < 0.45:
        return r.choice([f"₹ {cr:.2f} Cr", f"₹{cr:.2f} Crore", f"{cr:.2f} Cr"])
    if style < 0.70:
        return r.choice([f"₹ {lac:.0f} Lac", f"{lac:.1f} Lakh", f"₹{lac:.0f}L"])
    if style < 0.97:
        return "₹ " + _indian_commas(int(round(rupees, -3)))
    lo, hi = cr * 0.95, cr * 1.05  # occasional range
    return f"₹ {lo:.2f} - {hi:.2f} Cr"


def _indian_commas(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def _fmt_area(sqft: int, r: random.Random) -> str:
    x = r.random()
    if x < 0.65:
        return r.choice([f"{sqft} sq.ft", f"{sqft:,} sqft", f"{sqft} Sq. Ft."])
    if x < 0.85:
        return f"{sqft / 9:.0f} sq yd"
    return r.choice([f"{sqft / 10.7639:.0f} sq m", f"{sqft / 10.7639:.0f} sqm"])


def _fmt_bhk(bhk: int, r: random.Random) -> str:
    if bhk == 1 and r.random() < 0.2:
        return "1 RK"
    return r.choice([f"{bhk} BHK", f"{bhk}BHK", f"{bhk} Bhk"])


def _fmt_locality(name: str, r: random.Random) -> str:
    return r.choice(_VARIANTS.get(name, [name]))


def to_raw(p: dict, day: float, scraped_at: str, r: random.Random, listing_id: str | None = None) -> dict:
    price = true_price(p, day)
    # Agents revise asking prices in steps, not continuously.
    price = round(price * (1 + r.choice([0, 0, 0, -0.02, 0.01])), -4)
    if r.random() < 0.004:  # typo outliers
        price = r.choice([1, price * 100, price / 100])
    city = _LOC[p["locality"]][0]
    lid = listing_id or p["pid"]
    return {
        "listing_id": lid,
        "title": f"{p['bhk']} BHK Apartment in {p['locality']}",
        "price": _fmt_price(price, r),
        "area": _fmt_area(p["area_sqft"], r),
        "bhk": _fmt_bhk(p["bhk"], r),
        "locality": _fmt_locality(p["locality"], r),
        "city": city if r.random() > 0.05 else city.upper(),
        "builder": p["builder"] if r.random() > 0.04 else "",
        "status": p["status"] if r.random() > 0.5 else p["status"].upper().replace(" ", "_"),
        "age": f"{p['age_years']} years" if p["age_years"] else "New",
        "url": f"/listing/{lid}",
        "scraped_at": scraped_at,
        "source": SOURCE_NAME,
    }


def snapshot(props: list[dict], when: datetime) -> list[dict]:
    """Raw listings visible on the 'site' at a moment in time."""
    day = (when.date() - EPOCH).days + when.hour / 24 + when.minute / 1440
    stamp = when.replace(microsecond=0).isoformat()
    rows = []
    for p in props:
        if (day - p["start_day"]) % CYCLE_DAYS > p["duration"]:
            continue
        r = _rng(p["pid"], stamp)
        rows.append(to_raw(p, day, stamp, r))
        if p["duplicate"]:
            rows.append(to_raw(p, day, stamp, _rng(p["pid"], stamp, "dup"), listing_id=p["pid"] + "-D"))
    return rows


def history(props: list[dict], weeks: int = 16, end: date | None = None) -> list[dict]:
    """Weekly snapshots ending at `end`, used to seed the database with a trend."""
    end = end or date.today()
    rows = []
    for w in range(weeks, 0, -1):
        d = end - timedelta(weeks=w)
        rows.extend(snapshot(props, datetime(d.year, d.month, d.day, 6, 0)))
    return rows
