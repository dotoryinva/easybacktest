#!/usr/bin/env python
"""Full ticker-universe metadata bootstrap — light, fast, OHLCV-lazy.

This loads *all* ticker metadata for both markets (a few MB of Parquet that loads
instantly). It does NOT download OHLCV — that happens lazily on first request per
ticker (see `data_service.ensure_cached`). Run it in well under 15 minutes.

Sources
-------
US : NASDAQ Trader SymbolDirectory  (nasdaqlisted.txt + otherlisted.txt)
KR : FinanceDataReader StockListing  (KRX stocks + ETF/KR), one bulk call each
Indices : hand-curated per market (no free "list all indices" endpoint exists)

Usage
-----
    python scripts/bootstrap_metadata.py                 # both markets
    python scripts/bootstrap_metadata.py --markets US    # one market
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import data_service  # noqa: E402
from scripts.bootstrap_data import ALIASES, INDICES  # noqa: E402 - reuse curated lists

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", stream=sys.stdout
)
logger = logging.getLogger("bootstrap_metadata")

META_COLUMNS = [
    "ticker", "name_en", "name_ko", "market", "sector", "industry",
    "board", "exchange", "kind", "is_tradable", "aliases",
    "first_traded", "last_updated",
]

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

# otherlisted.txt Exchange codes -> human names.
US_EXCHANGE = {"A": "AMEX", "N": "NYSE", "P": "ARCA", "Z": "BATS", "V": "IEX"}

# Warrants / rights / units / preferreds / when-issued are not chartable equities.
_US_NON_EQUITY = re.compile(
    r"\b(warrant|warrants|right|rights|unit|units|when[- ]issued|preferred|depositary)\b",
    re.IGNORECASE,
)


def _blank_meta(**over) -> dict:
    row = {c: None for c in META_COLUMNS}
    row.update(
        sector=None, industry=None, aliases="", first_traded=pd.NaT,
        last_updated=pd.Timestamp.utcnow().tz_localize(None),
    )
    row.update(over)
    return row


def _indices_frame(market: str) -> pd.DataFrame:
    rows = []
    for ticker, mkt, name_en, name_ko in INDICES:
        if mkt != market:
            continue
        rows.append(
            _blank_meta(
                ticker=ticker, name_en=name_en, name_ko=name_ko, market=market,
                board="INDEX", exchange="INDEX", kind="index", is_tradable=False,
                aliases=ALIASES.get(ticker, ""),
            )
        )
    return pd.DataFrame(rows, columns=META_COLUMNS)


# --------------------------------------------------------------------------- #
# US — NASDAQ Trader SymbolDirectory
# --------------------------------------------------------------------------- #


def _read_symbol_dir(url: str) -> pd.DataFrame:
    df = pd.read_csv(url, sep="|", dtype=str, keep_default_na=False)
    # The final row is a "File Creation Time" footer, not a symbol.
    if len(df) and df.iloc[-1].astype(str).str.contains("File Creation Time").any():
        df = df.iloc[:-1]
    return df


def fetch_us_metadata() -> pd.DataFrame:
    rows: list[dict] = []

    for d in _read_symbol_dir(NASDAQ_LISTED_URL).to_dict("records"):
        symbol = str(d.get("Symbol", "")).strip()
        name = str(d.get("Security Name", "")).strip()
        if d.get("Test Issue") == "Y" or not symbol or "$" in symbol:
            continue
        if _US_NON_EQUITY.search(name):
            continue
        is_etf = d.get("ETF") == "Y"
        rows.append(
            _blank_meta(
                ticker=symbol, name_en=name or symbol, market="US",
                board="ETF" if is_etf else "US", exchange="NASDAQ",
                kind="etf" if is_etf else "stock", is_tradable=True,
                aliases=ALIASES.get(symbol, ""),
            )
        )

    for d in _read_symbol_dir(OTHER_LISTED_URL).to_dict("records"):
        symbol = str(d.get("ACT Symbol", "")).strip()
        name = str(d.get("Security Name", "")).strip()
        if d.get("Test Issue") == "Y" or not symbol or "$" in symbol:
            continue
        if _US_NON_EQUITY.search(name):
            continue
        is_etf = d.get("ETF") == "Y"
        exchange = US_EXCHANGE.get(str(d.get("Exchange", "")).strip(), "OTHER")
        rows.append(
            _blank_meta(
                ticker=symbol, name_en=name or symbol, market="US",
                board="ETF" if is_etf else "US", exchange=exchange,
                kind="etf" if is_etf else "stock", is_tradable=True,
                aliases=ALIASES.get(symbol, ""),
            )
        )

    df = pd.DataFrame(rows, columns=META_COLUMNS)
    return df.drop_duplicates(subset=["ticker"], keep="first")


# --------------------------------------------------------------------------- #
# KR — FinanceDataReader StockListing (bulk, includes names)
# --------------------------------------------------------------------------- #


def fetch_kr_metadata() -> pd.DataFrame:
    import FinanceDataReader as fdr  # noqa: PLC0415 - heavy import, script-only

    rows: list[dict] = []

    for d in fdr.StockListing("KRX").to_dict("records"):
        code = str(d.get("Code", "")).strip()
        name = str(d.get("Name", "")).strip()
        market_raw = str(d.get("Market", "")).upper()
        if not code or not name:
            continue
        board = (
            "KOSDAQ" if "KOSDAQ" in market_raw
            else "KONEX" if "KONEX" in market_raw
            else "KOSPI"
        )
        rows.append(
            _blank_meta(
                ticker=code, name_en=None, name_ko=name, market="KR",
                board=board, exchange=board, kind="stock", is_tradable=True,
                aliases=ALIASES.get(code, ""),
            )
        )

    for d in fdr.StockListing("ETF/KR").to_dict("records"):
        code = str(d.get("Symbol", "")).strip()
        name = str(d.get("Name", "")).strip()
        if not code or not name:
            continue
        rows.append(
            _blank_meta(
                ticker=code, name_en=None, name_ko=name, market="KR",
                board="ETF", exchange="ETF", kind="etf", is_tradable=True,
                aliases=ALIASES.get(code, ""),
            )
        )

    df = pd.DataFrame(rows, columns=META_COLUMNS)
    return df.drop_duplicates(subset=["ticker"], keep="first")


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #


def build_market(market: str) -> pd.DataFrame | None:
    indices = _indices_frame(market)
    try:
        listing = fetch_us_metadata() if market == "US" else fetch_kr_metadata()
    except Exception as exc:  # noqa: BLE001 - a source outage must not lose the indices
        logger.error("%s listing fetch failed (%s) — writing indices only", market, exc)
        listing = pd.DataFrame(columns=META_COLUMNS)

    # Curated indices first so their names/aliases win over any bare listing duplicate.
    combined = pd.concat([indices, listing], ignore_index=True)
    combined = combined.drop_duplicates(subset=["ticker"], keep="first")
    return combined


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--markets", default="KR,US")
    args = p.parse_args()
    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()]

    for market in markets:
        df = build_market(market)
        if df is None or df.empty:
            logger.warning("%s: nothing to write", market)
            continue
        data_service.write_tickers(df, market)
        logger.info(
            "%s: %d tickers (%d index, %d etf, %d stock) -> %s",
            market, len(df),
            int((df["kind"] == "index").sum()),
            int((df["kind"] == "etf").sum()),
            int((df["kind"] == "stock").sum()),
            data_service.tickers_file(market),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
