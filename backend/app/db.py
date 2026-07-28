"""SQLite connection + schema.

Column types and constraints are deliberately plain SQL so the same DDL migrates to
Postgres with only the `TEXT` timestamps swapped for `timestamptz`. Phase 2 tables
(portfolios, watchlists, users) hang off `user_id`, which is already carried on every
row even though Phase 1 has no auth.
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import settings

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS strategies (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT NOT NULL,
    language    TEXT NOT NULL,
    definition  TEXT NOT NULL,          -- full Strategy as JSON
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_strategies_user
    ON strategies (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id          TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL REFERENCES strategies (id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    market      TEXT NOT NULL,
    params      TEXT NOT NULL,          -- BacktestParams as JSON
    metrics     TEXT NOT NULL,          -- BacktestMetrics as JSON
    ran_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_strategy
    ON backtest_runs (strategy_id, ran_at DESC);

-- Popularity drives search tie-breaking and tells the nightly refresh which cold
-- tickers are worth keeping warm. One row per (market, ticker); bumped on every
-- OHLCV request (see data_service.record_query).
CREATE TABLE IF NOT EXISTS ticker_popularity (
    market          TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    query_count     INTEGER NOT NULL DEFAULT 0,
    last_queried_at TEXT NOT NULL,
    PRIMARY KEY (market, ticker)
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.sqlite_file, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    settings.sqlite_file.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
    logger.info("sqlite ready at %s", settings.sqlite_file)
