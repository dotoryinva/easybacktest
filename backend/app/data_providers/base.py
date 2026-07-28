"""DataProvider interface + normalisation helpers.

Providers are only ever used by the ingestion scripts. Request-time code reads the
local Parquet cache exclusively (see `services/data_service.py`).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)

OHLCV_COLUMNS = ["date", "open", "high", "low", "close", "volume", "adj_close"]


class DataProviderError(RuntimeError):
    """Raised when a provider cannot serve a request."""


class DataProvider(ABC):
    name: str = "base"

    @abstractmethod
    def get_ohlcv(
        self, ticker: str, market: str, start: date, end: date
    ) -> pd.DataFrame:
        """Return a frame with columns OHLCV_COLUMNS, sorted ascending by date."""

    @abstractmethod
    def list_universe(self, market: str) -> pd.DataFrame:
        """Return ticker metadata: [ticker, name_en, name_ko, market, sector, industry]."""


def normalize(df: pd.DataFrame, *, provider: str) -> pd.DataFrame:
    """Coerce a provider frame into the canonical schema."""
    if df is None or df.empty:
        raise DataProviderError(f"{provider} returned no rows")

    out = df.copy()

    # yfinance hands back a MultiIndex column frame for single tickers.
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = out.columns.get_level_values(0)

    out.columns = [str(c).strip().lower().replace(" ", "_") for c in out.columns]

    if "date" not in out.columns:
        out = out.reset_index()
        out.columns = [str(c).strip().lower().replace(" ", "_") for c in out.columns]
    if "date" not in out.columns:
        for candidate in ("index", "datetime", "날짜"):
            if candidate in out.columns:
                out = out.rename(columns={candidate: "date"})
                break
    if "date" not in out.columns:
        raise DataProviderError(f"{provider} frame has no date column: {list(out.columns)}")

    if "adj_close" not in out.columns:
        # KR sources publish split-adjusted prices with no separate dividend series;
        # treating close as adj_close is the standard convention there.
        out["adj_close"] = out["close"]

    missing = [c for c in OHLCV_COLUMNS if c not in out.columns]
    if missing:
        raise DataProviderError(f"{provider} frame missing columns {missing}")

    out = out[OHLCV_COLUMNS]
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None).dt.normalize()

    for col in ("open", "high", "low", "close", "adj_close", "volume"):
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["open", "high", "low", "close", "adj_close"])
    out = out[out["close"] > 0]
    out["volume"] = out["volume"].fillna(0)

    out = out.drop_duplicates(subset=["date"], keep="last")
    out = out.sort_values("date").reset_index(drop=True)

    if out.empty:
        raise DataProviderError(f"{provider} returned only unusable rows")
    return out


def has_gaps(df: pd.DataFrame, *, max_gap_ratio: float = 0.02) -> bool:
    """True when a suspicious share of rows carry NaN/zero prices."""
    if df.empty:
        return True
    bad = df[["open", "high", "low", "close"]].isna().any(axis=1) | (df["close"] <= 0)
    return bool(bad.mean() > max_gap_ratio)
