"""Answers to the project's analysis questions, as plain pandas functions.

All functions take the clean listings dataframe (as loaded from SQLite) so the
dashboard, notebooks and tests share one implementation.
"""
from __future__ import annotations

import pandas as pd


def latest(df: pd.DataFrame) -> pd.DataFrame:
    """Rows from the most recent crawl date (use the Source filter to pick a source)."""
    if df.empty:
        return df
    d = df[df["scraped_date"] == df["scraped_date"].max()]
    # if a source crawled several times that day, keep each listing's last sighting
    return d.sort_values("scraped_at").drop_duplicates(["source", "listing_id"], keep="last")


def locality_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Q1: most and least expensive localities per sq ft."""
    return (df.groupby(["city", "locality"])
              .agg(listings=("price", "size"),
                   median_ppsf=("price_per_sqft", "median"),
                   mean_ppsf=("price_per_sqft", "mean"),
                   median_price=("price", "median"))
              .round(0).reset_index()
              .sort_values("median_ppsf", ascending=False))


def bhk_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Q2: how price and price per sq ft change with BHK."""
    return (df.groupby("bhk")
              .agg(listings=("price", "size"),
                   median_area=("area_sqft", "median"),
                   median_price=("price", "median"),
                   median_ppsf=("price_per_sqft", "median"))
              .round(0).reset_index())


def builder_premium(df: pd.DataFrame, min_listings: int = 15) -> pd.DataFrame:
    """Q3: each builder's price per sq ft vs. the median of the localities it builds in.

    premium_pct > 0 means the builder prices above its neighbours.
    """
    d = df.copy()
    d["loc_median"] = d.groupby("locality")["price_per_sqft"].transform("median")
    d["rel"] = d["price_per_sqft"] / d["loc_median"] - 1
    out = (d.groupby("builder")
             .agg(listings=("rel", "size"), premium_pct=("rel", "median"))
             .reset_index())
    out = out[out["listings"] >= min_listings]
    out["premium_pct"] = (out["premium_pct"] * 100).round(1)
    return out.sort_values("premium_pct", ascending=False)


def status_compare(df: pd.DataFrame) -> pd.DataFrame:
    """Q4: ready-to-move vs under-construction, per locality."""
    p = df.pivot_table(index="locality", columns="status", values="price_per_sqft", aggfunc="median")
    if {"Ready to Move", "Under Construction"} <= set(p.columns):
        p["uc_discount_pct"] = ((1 - p["Under Construction"] / p["Ready to Move"]) * 100).round(1)
    return p.round(0).reset_index()


def weekly_trend(df: pd.DataFrame, by: str = "locality") -> pd.DataFrame:
    """Q5: median price per sq ft per week (and per group)."""
    d = df.copy()
    d["week"] = pd.to_datetime(d["scraped_date"]).dt.to_period("W-SUN").dt.start_time
    keys = ["week"] + ([by] if by else [])
    return d.groupby(keys)["price_per_sqft"].median().round(0).reset_index()


def repeat_listing_changes(df: pd.DataFrame, weeks: int = 4) -> pd.DataFrame:
    """Per-listing % change in asking price between ~`weeks` weeks ago and now.

    Comparing the same flat at two dates removes the noise of a different mix of
    flats being listed each week (a repeat-sales style index).
    """
    d = df.copy()
    d["week"] = pd.to_datetime(d["scraped_date"]).dt.to_period("W-SUN").dt.start_time
    if d["week"].nunique() < 2:
        return pd.DataFrame(columns=["listing_id", "locality", "change_pct"])
    end = d["week"].max()
    target = end - pd.Timedelta(weeks=weeks)
    past_weeks = d.loc[d["week"] <= target, "week"]
    start = past_weeks.max() if len(past_weeks) else d["week"].min()
    key = ["listing_id"]
    a = d[d["week"] == start].sort_values("scraped_at").drop_duplicates(key, keep="last")
    b = d[d["week"] == end].sort_values("scraped_at").drop_duplicates(key, keep="last")
    m = a[key + ["locality", "price_per_sqft"]].merge(b[key + ["price_per_sqft"]], on=key, suffixes=("_then", "_now"))
    m["change_pct"] = (m["price_per_sqft_now"] / m["price_per_sqft_then"] - 1) * 100
    return m


def price_movers(df: pd.DataFrame, weeks: int = 4, min_pairs: int = 5) -> pd.DataFrame:
    """Median like-for-like change in ₹/sq ft over the last `weeks` weeks, per locality."""
    m = repeat_listing_changes(df, weeks)
    if m.empty:
        return pd.DataFrame(columns=["locality", "pairs", "change_pct"])
    out = m.groupby("locality").agg(pairs=("change_pct", "size"), change_pct=("change_pct", "median"))
    out = out[out["pairs"] >= min_pairs]
    out["change_pct"] = out["change_pct"].round(1)
    return out.reset_index().sort_values("change_pct", ascending=False)


def top_deals(df: pd.DataFrame, n: int = 25, min_discount: float = 0.10) -> pd.DataFrame:
    """Listings priced at least `min_discount` below the median for the same locality and BHK."""
    d = df.copy()
    d["peer_ppsf"] = d.groupby(["locality", "bhk"])["price_per_sqft"].transform("median")
    d["peer_count"] = d.groupby(["locality", "bhk"])["price_per_sqft"].transform("size")
    d["discount_pct"] = ((1 - d["price_per_sqft"] / d["peer_ppsf"]) * 100).round(1)
    d = d[(d["peer_count"] >= 5) & (d["discount_pct"] >= min_discount * 100)]
    cols = ["title", "locality", "city", "bhk", "area_sqft", "price", "price_per_sqft",
            "peer_ppsf", "discount_pct", "builder", "status", "url"]
    return d.sort_values("discount_pct", ascending=False)[cols].head(n)


def insights(df_latest: pd.DataFrame, df_all: pd.DataFrame) -> list[str]:
    """A few plain-English findings for the README and the dashboard."""
    out = []
    if df_latest.empty:
        return out
    loc = locality_summary(df_latest)
    loc = loc[loc["listings"] >= 20]
    if len(loc) >= 2:
        hi, lo = loc.iloc[0], loc.iloc[-1]
        out.append(f"{hi.locality} is the most expensive locality at ₹{hi.median_ppsf:,.0f}/sq ft; "
                   f"{lo.locality} is the cheapest at ₹{lo.median_ppsf:,.0f}/sq ft "
                   f"({hi.median_ppsf / lo.median_ppsf:.1f}x).")
    three = df_latest[df_latest["bhk"] == 3]
    l3 = three.groupby("locality")["price_per_sqft"].agg(["median", "size"])
    l3 = l3[l3["size"] >= 15].sort_values("median")
    gur = l3[l3.index.isin(df_latest.loc[df_latest.city == "Gurugram", "locality"])]
    if len(gur) >= 2:
        a, b = gur.index[0], gur.index[-1]
        pct = (1 - gur.loc[a, "median"] / gur.loc[b, "median"]) * 100
        out.append(f"For 3 BHK units in Gurugram, {a} is {pct:.0f}% cheaper per sq ft than {b}.")
    sc = status_compare(df_latest)
    if "uc_discount_pct" in sc:
        out.append(f"Under-construction flats list at a median {sc['uc_discount_pct'].median():.0f}% "
                   f"discount per sq ft to ready-to-move flats in the same locality.")
    mv = price_movers(df_all)
    if len(mv) >= 2:
        up, down = mv.iloc[0], mv.iloc[-1]
        out.append(f"Over the last 4 weeks, asking prices for the same flats rose most in "
                   f"{up.locality} ({up.change_pct:+.1f}%) and least in {down.locality} ({down.change_pct:+.1f}%).")
    bp = builder_premium(df_latest)
    bp = bp[bp["builder"] != "Unknown"]
    if len(bp) >= 2:
        out.append(f"{bp.iloc[0].builder} prices {bp.iloc[0].premium_pct:+.1f}% vs. its locality median; "
                   f"{bp.iloc[-1].builder} {bp.iloc[-1].premium_pct:+.1f}%.")
    return out
