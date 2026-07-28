"""Provider registry + fetch-with-fallback used by the ingestion scripts."""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from .base import DataProvider, DataProviderError, has_gaps
from .fdr_provider import FDRProvider
from .pykrx_provider import PyKrxProvider
from .yfinance_provider import YFinanceProvider, top_us_etfs

logger = logging.getLogger(__name__)

_FDR = FDRProvider()
_PYKRX = PyKrxProvider()
_YF = YFinanceProvider()

# Order of attempt per market, per the ingestion spec.
PROVIDER_CHAIN: dict[str, list[DataProvider]] = {
    "KR": [_FDR, _PYKRX],
    "US": [_YF, _FDR],
}


def fetch_ohlcv(ticker: str, market: str, start: date, end: date) -> pd.DataFrame:
    """Try each provider for the market in order; fall through on failure or gaps."""
    chain = PROVIDER_CHAIN.get(market)
    if not chain:
        raise DataProviderError(f"unknown market {market!r}")

    errors: list[str] = []
    for provider in chain:
        try:
            df = provider.get_ohlcv(ticker, market, start, end)
        except DataProviderError as exc:
            errors.append(f"{provider.name}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{provider.name}: unexpected {exc}")
            continue

        if has_gaps(df):
            errors.append(f"{provider.name}: too many gaps ({len(df)} rows)")
            continue

        logger.debug("%s/%s served by %s (%d rows)", market, ticker, provider.name, len(df))
        return df

    raise DataProviderError(f"all providers failed for {market}/{ticker}: {'; '.join(errors)}")


def fetch_universe(market: str) -> pd.DataFrame:
    """Ticker metadata for a market, including the curated US ETF list."""
    listing = _FDR.list_universe(market)
    if market == "US":
        listing = pd.concat([listing, top_us_etfs(200)], ignore_index=True)
        listing = listing.drop_duplicates(subset=["ticker"], keep="first")
    return listing


__all__ = [
    "DataProvider",
    "DataProviderError",
    "FDRProvider",
    "PyKrxProvider",
    "YFinanceProvider",
    "PROVIDER_CHAIN",
    "fetch_ohlcv",
    "fetch_universe",
    "top_us_etfs",
]
