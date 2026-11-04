"""Fair-price model: compares Linear Regression with a Random Forest.

Training rows: each listing's most recent sighting in the last `weeks` weeks,
so one flat never appears in both train and test.
Target: log(price), which keeps errors proportional across ₹40 L and ₹8 Cr flats.
"""
from __future__ import annotations

import json
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .config import METRICS_PATH, MODEL_DIR, MODEL_PATH

NUMERIC = ["area_sqft", "bhk", "age_years"]
CATEGORICAL = ["locality", "builder", "status"]
FEATURES = NUMERIC + CATEGORICAL


def training_frame(df: pd.DataFrame, weeks: int = 4) -> pd.DataFrame:
    d = df.copy()
    d["scraped_date"] = pd.to_datetime(d["scraped_date"])
    d = d[d["scraped_date"] >= d["scraped_date"].max() - pd.Timedelta(weeks=weeks)]
    d = d.sort_values("scraped_at").drop_duplicates(["source", "listing_id"], keep="last")
    d["age_years"] = d["age_years"].fillna(0)
    return d[FEATURES + ["price"]].dropna()


def _prep(scale: bool) -> ColumnTransformer:
    num = StandardScaler() if scale else "passthrough"
    return ColumnTransformer([
        ("num", num, NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ])


def candidates() -> dict[str, Pipeline]:
    return {
        "Linear Regression (ridge)": Pipeline([("prep", _prep(True)), ("m", Ridge(alpha=1.0))]),
        "Random Forest": Pipeline([("prep", _prep(False)),
                                   ("m", RandomForestRegressor(n_estimators=150, min_samples_leaf=2,
                                                               n_jobs=-1, random_state=42))]),
    }


def train(df: pd.DataFrame) -> dict:
    data = training_frame(df)
    if len(data) < 200:
        raise ValueError(f"Need at least 200 clean listings to train, have {len(data)}")
    X, y = data[FEATURES], np.log(data["price"])
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)

    results, fitted = {}, {}
    for name, pipe in candidates().items():
        pipe.fit(Xtr, ytr)
        pred = np.exp(pipe.predict(Xte))
        true = np.exp(yte)
        results[name] = {
            "MAE_rupees": round(float(mean_absolute_error(true, pred))),
            "MAPE_pct": round(float(mean_absolute_percentage_error(true, pred) * 100), 2),
            "R2": round(float(r2_score(true, pred)), 3),
        }
        fitted[name] = pipe

    best = min(results, key=lambda k: results[k]["MAPE_pct"])  # lowest % error wins
    final = candidates()[best].fit(X, y)  # refit the winner on all rows
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": final, "name": best, "features": FEATURES}, MODEL_PATH, compress=3)
    metrics = {"trained_at": datetime.now().isoformat(timespec="seconds"),
               "rows": len(data), "test_rows": len(Xte), "best": best, "results": results}
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    return metrics


def load():
    return joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None


def predict(bundle, **features) -> dict:
    """Return the estimate and, for forests, an 80% range from the individual trees."""
    X = pd.DataFrame([{k: features[k] for k in FEATURES}])
    pipe = bundle["model"]
    est = float(np.exp(pipe.predict(X)[0]))
    out = {"estimate": est, "low": None, "high": None}
    m = pipe.named_steps["m"]
    if hasattr(m, "estimators_"):
        Xt = pipe.named_steps["prep"].transform(X)
        per_tree = np.exp([t.predict(Xt)[0] for t in m.estimators_])
        out["low"], out["high"] = float(np.percentile(per_tree, 10)), float(np.percentile(per_tree, 90))
    return out
