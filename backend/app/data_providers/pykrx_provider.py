"""pykrx provider — KR fallback when FinanceDataReader fails or returns gaps."""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from .base import DataProvider, DataProviderError, normalize

logger = logging.getLogger(__name__)

_KR_COLUMN_MAP = {
    "시가": "open",
    "고가": "high",
    "저가": "low",
    "종가": "close",
    "거래량": "volume",
}


class PyKrxProvider(DataProvider):
    name = "pykrx"

    def get_ohlcv(
        self, ticker: str, market: str, start: date, end: date
    ) -> pd.DataFrame:
        if market != "KR":
            raise DataProviderError("pykrx only serves the KR market")

        from pykrx import stock

        try:
            df = stock.get_market_ohlcv(
                start.strftime("%Y%m%d"),
                end.strftime("%Y%m%d"),
                ticker,
                adjusted=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise DataProviderError(f"pykrx failed for {ticker}: {exc}") from exc

        if df is None or df.empty:
            raise DataProviderError(f"pykrx returned no rows for {ticker}")

        df = df.rename(columns=_KR_COLUMN_MAP)
        df.index.name = "date"
        return normalize(df.reset_index(), provider="pykrx")

    def list_universe(self, market: str) -> pd.DataFrame:
        if market != "KR":
            raise DataProviderError("pykrx only serves the KR market")

        from pykrx import stock

        today = date.today().strftime("%Y%m%d")
        rows = []
        for board in ("KOSPI", "KOSDAQ"):
            for code in stock.get_market_ticker_list(today, market=board):
                rows.append(
                    {
                        "ticker": code,
                        "name_ko": stock.get_market_ticker_name(code),
                        "name_en": stock.get_market_ticker_name(code),
                        "market": "KR",
                        "sector": None,
                        "industry": None,
                        "board": board,
                    }
                )
        return pd.DataFrame(rows)
