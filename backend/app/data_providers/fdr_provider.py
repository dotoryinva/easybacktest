"""FinanceDataReader provider — primary for KR, fallback for US."""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from .base import DataProvider, DataProviderError, normalize

logger = logging.getLogger(__name__)


def _pick(df: pd.DataFrame, *candidates: str) -> pd.Series | None:
    for c in candidates:
        if c in df.columns:
            return df[c]
    return None


class FDRProvider(DataProvider):
    name = "fdr"

    def get_ohlcv(
        self, ticker: str, market: str, start: date, end: date
    ) -> pd.DataFrame:
        import FinanceDataReader as fdr

        try:
            df = fdr.DataReader(ticker, str(start), str(end))
        except Exception as exc:  # noqa: BLE001 - provider surface is wide
            raise DataProviderError(f"fdr failed for {ticker}: {exc}") from exc
        return normalize(df, provider="fdr")

    def list_universe(self, market: str) -> pd.DataFrame:
        import FinanceDataReader as fdr

        if market == "KR":
            frames = []
            for board, limit in (("KOSPI", 500), ("KOSDAQ", 300)):
                listing = fdr.StockListing(board)
                listing = self._normalize_kr_listing(listing, board)
                marcap = _pick(listing, "Marcap", "MarketCap")
                if marcap is not None:
                    listing = listing.assign(_marcap=pd.to_numeric(marcap, errors="coerce"))
                    listing = listing.sort_values("_marcap", ascending=False)
                frames.append(listing.head(limit).drop(columns=["_marcap"], errors="ignore"))
            return pd.concat(frames, ignore_index=True)

        frames = []
        for board in ("S&P500", "NASDAQ"):
            try:
                listing = fdr.StockListing(board)
            except Exception as exc:  # noqa: BLE001
                logger.warning("fdr StockListing(%s) failed: %s", board, exc)
                continue
            frames.append(self._normalize_us_listing(listing))
        if not frames:
            raise DataProviderError("fdr could not list any US universe")
        out = pd.concat(frames, ignore_index=True)
        return out.drop_duplicates(subset=["ticker"], keep="first")

    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize_kr_listing(df: pd.DataFrame, board: str) -> pd.DataFrame:
        code = _pick(df, "Code", "Symbol")
        name = _pick(df, "Name")
        if code is None or name is None:
            raise DataProviderError(f"unexpected KR listing columns: {list(df.columns)}")
        out = pd.DataFrame(
            {
                "ticker": code.astype(str).str.zfill(6),
                "name_ko": name.astype(str),
                "name_en": name.astype(str),
                "market": "KR",
                "sector": _pick(df, "Sector", "Industry"),
                "industry": _pick(df, "Industry", "Sector"),
                "board": board,
            }
        )
        marcap = _pick(df, "Marcap", "MarketCap")
        if marcap is not None:
            out["Marcap"] = pd.to_numeric(marcap, errors="coerce")
        return out

    @staticmethod
    def _normalize_us_listing(df: pd.DataFrame) -> pd.DataFrame:
        symbol = _pick(df, "Symbol", "Code")
        name = _pick(df, "Name")
        if symbol is None or name is None:
            raise DataProviderError(f"unexpected US listing columns: {list(df.columns)}")
        return pd.DataFrame(
            {
                "ticker": symbol.astype(str).str.upper(),
                "name_en": name.astype(str),
                "name_ko": None,
                "market": "US",
                "sector": _pick(df, "Sector", "Industry"),
                "industry": _pick(df, "Industry", "Sector"),
                "board": "US",
            }
        )
