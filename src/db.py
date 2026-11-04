"""SQLite storage. One row per listing per crawl, so price history is kept."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id      TEXT NOT NULL,
    title           TEXT,
    locality        TEXT NOT NULL,
    city            TEXT NOT NULL,
    bhk             INTEGER NOT NULL,
    area_sqft       REAL NOT NULL,
    price           REAL NOT NULL,
    price_per_sqft  REAL NOT NULL,
    builder         TEXT,
    status          TEXT,
    age_years       REAL,
    url             TEXT,
    source          TEXT NOT NULL,
    scraped_at      TEXT NOT NULL,
    scraped_date    TEXT NOT NULL,
    UNIQUE (source, listing_id, scraped_at)
);
CREATE INDEX IF NOT EXISTS idx_listings_date     ON listings (scraped_date);
CREATE INDEX IF NOT EXISTS idx_listings_locality ON listings (locality, scraped_date);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    source      TEXT NOT NULL,
    raw_rows    INTEGER,
    clean_rows  INTEGER,
    inserted    INTEGER,
    report      TEXT
);
"""


@contextmanager
def connect(path: Path | str = DB_PATH):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


def insert_listings(df: pd.DataFrame, path: Path | str = DB_PATH) -> int:
    """Insert clean rows; rows already stored for the same crawl are skipped."""
    if df.empty:
        return 0
    cols = list(df.columns)
    sql = f"INSERT OR IGNORE INTO listings ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
    rows = [tuple(None if pd.isna(v) else v for v in r) for r in df.itertuples(index=False)]
    with connect(path) as con:
        before = con.total_changes
        con.executemany(sql, rows)
        return con.total_changes - before


def log_run(source: str, report: dict, inserted: int, path: Path | str = DB_PATH) -> None:
    with connect(path) as con:
        con.execute(
            "INSERT INTO crawl_runs (started_at, source, raw_rows, clean_rows, inserted, report) VALUES (?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), source, report.get("raw_rows"),
             report.get("clean_rows"), inserted, json.dumps(report)),
        )


def load_listings(path: Path | str = DB_PATH) -> pd.DataFrame:
    with connect(path) as con:
        return pd.read_sql_query("SELECT * FROM listings", con)


def load_runs(path: Path | str = DB_PATH) -> pd.DataFrame:
    with connect(path) as con:
        return pd.read_sql_query("SELECT * FROM crawl_runs ORDER BY id DESC", con)
