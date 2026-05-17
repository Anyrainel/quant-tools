"""
Data cache layer — SQLite-backed, immutable for past dates.

Usage:
    from cache import get_cached, get_latest_before, put_cached, put_bulk, is_cached_series

DB location: data/cache.db
Table: indicator_cache(source, series, date, value, fetched_at)
"""
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "cache.db"


# ── Connection ────────────────────────────────────────────────────────────────


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS indicator_cache (
            source     TEXT NOT NULL,
            series     TEXT NOT NULL,
            date       TEXT NOT NULL,
            value      REAL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (source, series, date)
        )
    """)
    conn.commit()
    return conn


# ── Public API ────────────────────────────────────────────────────────────────


def get_cached(source: str, series: str, date_str: str) -> Optional[float]:
    """Return cached value for exact (source, series, date) match, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM indicator_cache WHERE source=? AND series=? AND date=?",
            (source, series, date_str),
        ).fetchone()
        return row[0] if row is not None else None


def get_latest_before(source: str, series: str, date_str: str):
    """Return (value, date_str) for the most recent observation <= date_str, or (None, None)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT value, date FROM indicator_cache "
            "WHERE source=? AND series=? AND date<=? AND value IS NOT NULL "
            "ORDER BY date DESC LIMIT 1",
            (source, series, date_str),
        ).fetchone()
        return (row[0], row[1]) if row else (None, None)


def put_cached(source: str, series: str, date_str: str, value: Optional[float]) -> None:
    """Store a single observation. Overwrites today; ignores if past date already cached."""
    today = str(date.today())
    now = datetime.utcnow().isoformat()
    sql = (
        "INSERT OR REPLACE INTO indicator_cache (source,series,date,value,fetched_at) VALUES (?,?,?,?,?)"
        if date_str == today
        else "INSERT OR IGNORE INTO indicator_cache (source,series,date,value,fetched_at) VALUES (?,?,?,?,?)"
    )
    with _connect() as conn:
        conn.execute(sql, (source, series, date_str, value, now))
        conn.commit()


def put_bulk(source: str, series: str, obs: dict) -> None:
    """Cache a full series dict {date_str_or_Timestamp: value} efficiently.

    Past dates use INSERT OR IGNORE (immutable).
    Today's date uses INSERT OR REPLACE (re-fetch OK).
    """
    today = str(date.today())
    now = datetime.utcnow().isoformat()
    past_rows = []
    today_row = None
    for dt, val in obs.items():
        dt_str = str(dt)[:10]
        float_val = float(val) if val is not None else None
        if dt_str == today:
            today_row = (source, series, dt_str, float_val, now)
        else:
            past_rows.append((source, series, dt_str, float_val, now))

    with _connect() as conn:
        if past_rows:
            conn.executemany(
                "INSERT OR IGNORE INTO indicator_cache (source,series,date,value,fetched_at) VALUES (?,?,?,?,?)",
                past_rows,
            )
        if today_row:
            conn.execute(
                "INSERT OR REPLACE INTO indicator_cache (source,series,date,value,fetched_at) VALUES (?,?,?,?,?)",
                today_row,
            )
        conn.commit()


def is_cached_series(source: str, series: str) -> bool:
    """Return True if we have any observations for this source/series."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM indicator_cache WHERE source=? AND series=? LIMIT 1",
            (source, series),
        ).fetchone()
        return row is not None


def preload_series(source: str, series: str):
    """Load all observations for a series into a sorted list of (date_str, value) tuples."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT date, value FROM indicator_cache "
            "WHERE source=? AND series=? AND value IS NOT NULL ORDER BY date",
            (source, series),
        ).fetchall()
        return rows  # [(date_str, value), ...]
