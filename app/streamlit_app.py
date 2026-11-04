"""Delhi NCR Real Estate Price Analyzer - Streamlit dashboard.

    streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import branca.colormap as cm
import folium
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import analysis as A  # noqa: E402
from src import db  # noqa: E402
from src.config import LOCALITY_INFO, METRICS_PATH  # noqa: E402
from src.model import load as load_model, predict  # noqa: E402

st.set_page_config(page_title="NCR Price Analyzer", page_icon="🏙️", layout="wide")

# ---------------------------------------------------------------- chart style
# Reference palette: one hue for single-series magnitude, fixed categorical
# order for identity, blue<->red with a gray midpoint for +/- change.
BLUE = "#2a78d6"
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # max 4 series per chart
SEQ = ["#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DIVERGING = [[0, "#d03b3b"], [0.5, "#f0efec"], [1, "#2a78d6"]]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e9e8e4"


def style(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=36, b=8),
        font=dict(color=INK, size=13), title_font=dict(size=15, color=INK),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor="white", font_color=INK), legend_title_text="",
        legend=dict(orientation="h", y=-0.15),
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont_color=INK2)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont_color=INK2)
    return fig


def inr(x: float) -> str:
    if pd.isna(x):
        return "-"
    return f"₹{x / 1e7:.2f} Cr" if x >= 1e7 else f"₹{x / 1e5:.1f} L"


# ---------------------------------------------------------------- data

@st.cache_data(ttl=60, show_spinner=False)
def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    return db.load_listings(), db.load_runs()


@st.cache_resource(show_spinner=False)
def model_bundle(mtime: float):
    return load_model()


df_all, runs = load()

st.title("Delhi NCR Real Estate Price Analyzer")

if df_all.empty:
    st.warning("The database is empty. Run `python pipeline.py seed` for demo data, "
               "or start the practice site and run `python pipeline.py crawl`.")
    st.stop()

sources = sorted(df_all["source"].unique())
if "sample" in sources:
    st.info("Includes **synthetic sample data** generated for the demo. These are not real listings "
            "or real market prices. Crawl a permitted source to replace it.", icon="ℹ️")

last_run = runs["started_at"].iloc[0] if not runs.empty else "never"
top = st.columns([3, 1])
top[0].caption(f"Last pipeline run: **{last_run}** · {len(df_all):,} rows in database · "
               f"{df_all['scraped_date'].nunique()} crawl dates · sources: {', '.join(sources)}")
if top[1].button("↻ Refresh data", width="stretch"):
    load.clear()
    st.rerun()

# ---------------------------------------------------------------- filters

with st.sidebar:
    st.header("Filters")
    src = st.multiselect("Source", sources, default=sources)
    cities = sorted(df_all["city"].unique())
    city = st.multiselect("City", cities, default=cities)
    locs_avail = sorted(df_all[df_all["city"].isin(city)]["locality"].unique())
    loc = st.multiselect("Locality", locs_avail, placeholder="All localities")
    bhks = sorted(int(b) for b in df_all["bhk"].unique())
    bhk = st.multiselect("BHK", bhks, default=bhks)
    max_cr = float(max(1.0, round(df_all["price"].quantile(0.995) / 1e7 + 0.5)))
    budget = st.slider("Budget (₹ Cr)", 0.0, max_cr, (0.0, max_cr), step=0.25)
    builders = sorted(df_all["builder"].unique())
    builder = st.multiselect("Builder", builders, placeholder="All builders")
    status = st.multiselect("Status", sorted(df_all["status"].unique()),
                            default=sorted(df_all["status"].unique()))


def apply(d: pd.DataFrame) -> pd.DataFrame:
    m = (d["source"].isin(src) & d["city"].isin(city) & d["bhk"].isin(bhk)
         & d["price"].between(budget[0] * 1e7, budget[1] * 1e7) & d["status"].isin(status))
    if loc:
        m &= d["locality"].isin(loc)
    if builder:
        m &= d["builder"].isin(builder)
    return d[m]


hist = apply(df_all)
now = A.latest(hist)

if now.empty:
    st.warning("No listings match these filters.")
    st.stop()

# ---------------------------------------------------------------- KPIs

movers = A.price_movers(hist)
pairs = A.repeat_listing_changes(hist)
chg = pairs["change_pct"].median() if len(pairs) >= 20 else None

k = st.columns(4)
k[0].metric("Active listings (latest crawl)", f"{len(now):,}")
k[1].metric("Median price / sq ft", f"₹{now['price_per_sqft'].median():,.0f}",
            f"{chg:+.1f}% same flats, 4 wks" if chg is not None else None)
k[2].metric("Median price", inr(now["price"].median()))
k[3].metric("Median size", f"{now['area_sqft'].median():,.0f} sq ft")

tabs = st.tabs(["Overview", "Trends", "Map", "Top deals", "Builders & status", "Price predictor", "Pipeline"])

# ---------------------------------------------------------------- overview
with tabs[0]:
    ls = A.locality_summary(now)
    c1, c2 = st.columns([3, 2])
    fig = px.bar(ls.sort_values("median_ppsf"), x="median_ppsf", y="locality", orientation="h",
                 title="Median price per sq ft by locality (latest crawl)",
                 labels={"median_ppsf": "₹ per sq ft", "locality": ""},
                 hover_data={"city": True, "listings": True, "median_price": ":,.0f"},
                 color_discrete_sequence=[BLUE])
    fig.update_traces(marker_line_width=0, texttemplate="₹%{x:,.0f}", textposition="outside",
                      textfont_color=INK2, cliponaxis=False)
    fig.update_xaxes(range=[0, ls["median_ppsf"].max() * 1.15])
    c1.plotly_chart(style(fig, max(380, 26 * len(ls) + 80)), width="stretch")

    sample = now.sample(min(len(now), 2500), random_state=1).assign(price_cr=lambda d: d["price"] / 1e7)
    fig = px.scatter(sample, x="area_sqft", y="price_cr", title="Area vs price",
                     labels={"area_sqft": "Area (sq ft)", "price_cr": "Price (₹ Cr)"},
                     hover_data={"locality": True, "bhk": True, "price_per_sqft": ":,.0f"},
                     color_discrete_sequence=[BLUE], opacity=0.45)
    fig.update_traces(marker_size=8, marker_line=dict(width=1, color="#fcfcfb"))
    c2.plotly_chart(style(fig), width="stretch")

    bs = A.bhk_summary(now)
    c2.dataframe(bs.rename(columns={"bhk": "BHK", "listings": "Listings", "median_area": "Median sq ft",
                                    "median_price": "Median ₹", "median_ppsf": "Median ₹/sq ft"}),
                 hide_index=True, width="stretch",
                 column_config={"Median ₹": st.column_config.NumberColumn(format="localized"),
                                "Median ₹/sq ft": st.column_config.NumberColumn(format="localized"),
                                "Median sq ft": st.column_config.NumberColumn(format="localized")})

    st.subheader("Findings")
    for line in A.insights(now, hist):
        st.markdown(f"- {line}")

# ---------------------------------------------------------------- trends
with tabs[1]:
    tr = A.weekly_trend(hist)
    default = (movers["locality"].head(2).tolist() + movers["locality"].tail(2).tolist()) if len(movers) else []
    pick = st.multiselect("Compare localities (up to 4)", sorted(tr["locality"].unique()),
                          default=default[:4], max_selections=4)
    if pick:
        t = tr[tr["locality"].isin(pick)]
        fig = px.line(t, x="week", y="price_per_sqft", color="locality", markers=True,
                      category_orders={"locality": pick},
                      color_discrete_sequence=CATEGORICAL,
                      title="Weekly median price per sq ft",
                      labels={"week": "", "price_per_sqft": "₹ per sq ft"})
        fig.update_traces(line_width=2, marker_size=8)
        fig.update_layout(hovermode="x unified")
        st.plotly_chart(style(fig, 420), width="stretch")

    if len(movers):
        fig = px.bar(movers.sort_values("change_pct"), x="change_pct", y="locality", orientation="h",
                     color="change_pct", color_continuous_scale=DIVERGING,
                     range_color=[-movers["change_pct"].abs().max(), movers["change_pct"].abs().max()],
                     title="Asking-price change over 4 weeks (same flats, median)",
                     labels={"change_pct": "% change", "locality": ""},
                     hover_data={"pairs": True})
        fig.update_traces(texttemplate="%{x:+.1f}%", textposition="outside", textfont_color=INK2,
                          cliponaxis=False)
        fig.update_layout(coloraxis_showscale=False)
        mlim = max(0.5, movers["change_pct"].abs().max())
        fig.update_xaxes(range=[-mlim * 1.45, mlim * 1.45])
        st.plotly_chart(style(fig, max(380, 26 * len(movers) + 80)), width="stretch")
    else:
        st.caption("Trend needs at least two crawl weeks. Run the crawler again next week, "
                   "or `pipeline.py seed` for demo history.")

# ---------------------------------------------------------------- map
with tabs[2]:
    ls = A.locality_summary(now)
    ls["lat"] = ls["locality"].map(lambda l: LOCALITY_INFO.get(l, {}).get("lat"))
    ls["lon"] = ls["locality"].map(lambda l: LOCALITY_INFO.get(l, {}).get("lon"))
    unknown = ls[ls["lat"].isna()]["locality"].tolist()
    ls = ls.dropna(subset=["lat"])
    lo_, hi_ = ls["median_ppsf"].min(), ls["median_ppsf"].max()
    cmap = cm.LinearColormap(SEQ, vmin=lo_, vmax=hi_, caption="Median ₹ per sq ft")
    fmap = folium.Map(location=[28.55, 77.22], zoom_start=10, tiles="OpenStreetMap")
    for r in ls.itertuples():
        folium.CircleMarker(
            location=[r.lat, r.lon], radius=6 + 14 * (r.listings / ls["listings"].max()) ** 0.5,
            color="#fcfcfb", weight=2, fill=True, fill_color=cmap(r.median_ppsf), fill_opacity=0.9,
            tooltip=f"<b>{r.locality}</b>, {r.city}<br>₹{r.median_ppsf:,.0f}/sq ft · {r.listings} listings",
        ).add_to(fmap)
    cmap.add_to(fmap)
    st.markdown("**Localities coloured by median price per sq ft** (bubble size = listings)")
    st_folium(fmap, height=560, use_container_width=True, returned_objects=[])
    st.caption("Coordinates are approximate locality centres.")
    if unknown:
        st.caption(f"Not on the map (add coordinates in src/config.py): {', '.join(unknown)}")

# ---------------------------------------------------------------- deals
with tabs[3]:
    min_disc = st.slider("Minimum discount vs. same locality and BHK", 5, 30, 12, format="%d%%")
    deals = A.top_deals(now, n=50, min_discount=min_disc / 100)
    st.caption(f"{len(deals)} listings priced at least {min_disc}% below the median ₹/sq ft "
               "of comparable flats (same locality and BHK) in the latest crawl. "
               "Big discounts can also mean data errors or missing details, so check the listing.")
    show = deals.assign(price=deals["price"].map(inr))
    st.dataframe(show, hide_index=True, width="stretch",
                 column_config={
                     "url": st.column_config.LinkColumn("Link", display_text="open"),
                     "price_per_sqft": st.column_config.NumberColumn("₹/sq ft", format="%d"),
                     "peer_ppsf": st.column_config.NumberColumn("Peer ₹/sq ft", format="%d"),
                     "discount_pct": st.column_config.NumberColumn("Discount", format="%.1f%%"),
                     "area_sqft": st.column_config.NumberColumn("Sq ft", format="%d"),
                 })

# ---------------------------------------------------------------- builders / status
with tabs[4]:
    c1, c2 = st.columns(2)
    bp = A.builder_premium(now)
    if len(bp):
        lim = max(1.0, bp["premium_pct"].abs().max())
        fig = px.bar(bp.sort_values("premium_pct"), x="premium_pct", y="builder", orientation="h",
                     color="premium_pct", color_continuous_scale=DIVERGING, range_color=[-lim, lim],
                     title="Builder premium vs. locality median ₹/sq ft",
                     labels={"premium_pct": "% vs locality median", "builder": ""},
                     hover_data={"listings": True})
        fig.update_traces(texttemplate="%{x:+.1f}%", textposition="outside", textfont_color=INK2,
                          cliponaxis=False)
        fig.update_layout(coloraxis_showscale=False)
        fig.update_xaxes(range=[-lim * 1.45, lim * 1.45])
        c1.plotly_chart(style(fig), width="stretch")
    sc = A.status_compare(now)
    c2.markdown("**Ready to move vs under construction (median ₹/sq ft)**")
    c2.dataframe(sc, hide_index=True, width="stretch",
                 column_config={"uc_discount_pct": st.column_config.NumberColumn(
                     "UC discount", format="%.1f%%")})

# ---------------------------------------------------------------- predictor
with tabs[5]:
    mtime = METRICS_PATH.stat().st_mtime if METRICS_PATH.exists() else 0
    bundle = model_bundle(mtime)
    if bundle is None:
        st.info("No model yet. Run `python pipeline.py train`.")
    else:
        metrics = json.loads(METRICS_PATH.read_text())
        st.caption(f"Model: **{bundle['name']}**, trained {metrics['trained_at']} on "
                   f"{metrics['rows']:,} listings.")
        st.dataframe(pd.DataFrame(metrics["results"]).T.rename_axis("Model").reset_index(),
                     hide_index=True, width="stretch",
                     column_config={"MAE_rupees": st.column_config.NumberColumn("MAE (₹)", format="%d"),
                                    "MAPE_pct": st.column_config.NumberColumn("MAPE", format="%.1f%%"),
                                    "R2": st.column_config.NumberColumn("R²", format="%.3f")})
        with st.form("predict"):
            f = st.columns(3)
            p_loc = f[0].selectbox("Locality", sorted(df_all["locality"].unique()))
            p_bhk = f[1].selectbox("BHK", [1, 2, 3, 4, 5], index=2)
            p_area = f[2].number_input("Area (sq ft)", 300, 10000, 1650, step=50)
            g = st.columns(3)
            p_builder = g[0].selectbox("Builder", sorted(df_all["builder"].unique()))
            p_status = g[1].selectbox("Status", ["Ready to Move", "Under Construction"])
            p_age = g[2].number_input("Age (years)", 0, 40, 0 if p_status != "Ready to Move" else 3)
            go_ = st.form_submit_button("Estimate fair price", type="primary")
        if go_:
            r = predict(bundle, locality=p_loc, bhk=p_bhk, area_sqft=p_area, builder=p_builder,
                        status=p_status, age_years=p_age)
            peers = now[(now["locality"] == p_loc) & (now["bhk"] == p_bhk)]
            m = st.columns(3)
            m[0].metric("Estimated fair price", inr(r["estimate"]))
            if r["low"]:
                m[1].metric("Likely range (80%)", f"{inr(r['low'])} – {inr(r['high'])}")
            m[2].metric("Implied ₹/sq ft", f"₹{r['estimate'] / p_area:,.0f}",
                        f"{(r['estimate'] / p_area / peers['price_per_sqft'].median() - 1) * 100:+.1f}% vs peers"
                        if len(peers) else None, delta_color="off")

# ---------------------------------------------------------------- pipeline
with tabs[6]:
    st.markdown("**Recent pipeline runs**")
    if not runs.empty:
        r = runs.copy()
        rep = r["report"].map(json.loads).apply(pd.Series)
        cols = [c for c in rep.columns if c.startswith("dropped_")]
        st.dataframe(pd.concat([r[["started_at", "source", "raw_rows", "clean_rows", "inserted"]], rep[cols]], axis=1)
                     .rename(columns=lambda c: c.replace("dropped_", "drop: ").replace("_", " ")),
                     hide_index=True, width="stretch")
    per = df_all.groupby(["scraped_date", "source"]).size().reset_index(name="rows")
    fig = px.bar(per, x="scraped_date", y="rows", color="source", color_discrete_sequence=CATEGORICAL,
                 title="Clean rows stored per crawl date", labels={"scraped_date": "", "rows": "rows"})
    fig.update_traces(marker_line_width=2, marker_line_color="#fcfcfb")
    st.plotly_chart(style(fig, 320), width="stretch")
    st.caption(f"Page rendered {datetime.now():%Y-%m-%d %H:%M:%S}. Data cache refreshes every 60 s.")
