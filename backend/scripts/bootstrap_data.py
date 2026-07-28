#!/usr/bin/env python
"""Initial OHLCV download into the local Parquet cache.

Examples
--------
# Dev subset used during development (step 1 of the build order):
python scripts/bootstrap_data.py --tickers AAPL:US,MSFT:US,KO:US,005930:KR,000660:KR --years 5

# Full Phase 1 universe (KOSPI 500 + KOSDAQ 300 + S&P 500 + NASDAQ 100 + 200 ETFs):
python scripts/bootstrap_data.py --years 15
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_providers import DataProviderError, fetch_ohlcv, fetch_universe  # noqa: E402
from app.data_providers.yfinance_provider import top_us_etfs  # noqa: E402
from app.services import data_service  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", stream=sys.stdout
)
logger = logging.getLogger("bootstrap")

# FDR has no NASDAQ-100 endpoint, so the constituent list is pinned here.
NASDAQ_100 = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT", "AMD", "AMGN",
    "AMZN", "ANSS", "APP", "ARM", "ASML", "AVGO", "AXON", "AZN", "BIIB", "BKNG",
    "BKR", "CCEP", "CDNS", "CDW", "CEG", "CHTR", "CMCSA", "COST", "CPRT", "CRWD",
    "CSCO", "CSGP", "CSX", "CTAS", "CTSH", "DASH", "DDOG", "DLTR", "DXCM", "EA",
    "EXC", "FANG", "FAST", "FTNT", "GEHC", "GFS", "GILD", "GOOG", "GOOGL", "HON",
    "IDXX", "ILMN", "INTC", "INTU", "ISRG", "KDP", "KHC", "KLAC", "LIN", "LRCX",
    "LULU", "MAR", "MCHP", "MDB", "MDLZ", "MELI", "META", "MNST", "MRNA", "MRVL",
    "MSFT", "MU", "NFLX", "NVDA", "NXPI", "ODFL", "ON", "ORLY", "PANW", "PAYX",
    "PCAR", "PDD", "PEP", "PYPL", "QCOM", "REGN", "ROP", "ROST", "SBUX", "SNPS",
    "TEAM", "TMUS", "TSLA", "TTD", "TTWO", "TXN", "VRSK", "VRTX", "WBD", "WDAY",
    "XEL", "ZS",
]

# --------------------------------------------------------------------------- #
# Curated universe (PROJECT_SPEC.md → "Ticker Universe")
# --------------------------------------------------------------------------- #

# (ticker, market, name_en, name_ko)
INDICES: list[tuple[str, str, str, str | None]] = [
    ("^GSPC", "US", "S&P 500", "S&P 500 지수"),
    ("^IXIC", "US", "NASDAQ Composite", "나스닥 종합지수"),
    ("^DJI", "US", "Dow Jones Industrial Average", "다우존스 산업평균지수"),
    ("^RUT", "US", "Russell 2000", "러셀 2000"),
    ("^VIX", "US", "CBOE Volatility Index", "변동성지수(VIX)"),
    ("KS11", "KR", "KOSPI Composite Index", "코스피"),
    ("KQ11", "KR", "KOSDAQ Composite Index", "코스닥"),
    ("KS200", "KR", "KOSPI 200", "코스피 200"),
    ("KQ150", "KR", "KOSDAQ 150", "코스닥 150"),
]

BROAD_ETFS_US = [
    "SPY", "VOO", "IVV", "QQQ", "QQQM", "DIA", "IWM", "VTI", "VEA",
    "VWO", "VXUS", "TLT", "IEF", "SHY", "GLD", "SLV", "USO", "DBC",
]

SECTOR_ETFS_US = [
    "XLK", "XLF", "XLE", "XLV", "XLP", "XLY", "XLI", "XLU", "XLB", "XLRE", "XLC",
]

THEME_ETFS_US = ["EWZ", "EWJ", "EWG", "MCHI", "INDA", "EEM", "EFA", "ARKK", "SOXX", "SMH"]

# (code, name_ko)
KR_ETFS: list[tuple[str, str]] = [
    ("069500", "KODEX 200"),
    ("102110", "TIGER 200"),
    ("122630", "KODEX 레버리지"),
    ("114800", "KODEX 인버스"),
    ("226980", "KODEX 200TR"),
    ("305720", "KODEX 200선물인버스2X"),
    ("360750", "TIGER 미국S&P500"),
    ("379800", "KODEX 미국S&P500TR"),
    ("381180", "TIGER 미국테크TOP10"),
    ("133690", "TIGER 미국나스닥100"),
    ("371460", "TIGER 차이나전기차SOLACTIVE"),
    ("305080", "TIGER 미국채10년선물"),
    ("132030", "KODEX 골드선물"),
]

# Phase 1 authors aliases for the top 20 tickers only; everything else relies on
# ticker + name matching.
ALIASES: dict[str, str] = {
    "SPY": "SPY;S&P 500 ETF;에스피와이;미국S&P500ETF",
    "QQQ": "QQQ;NASDAQ 100 ETF;나스닥100;큐큐큐;미국나스닥ETF",
    "VOO": "VOO;Vanguard S&P 500;뱅가드S&P500;미국S&P500ETF",
    "VTI": "VTI;Total Stock Market;미국전체시장ETF;뱅가드토탈",
    "^GSPC": "S&P 500;S&P;SPX;SP500;스탠다드앤푸어스;스탠다드앤푸어스500;에스앤피",
    "^IXIC": "NASDAQ;NASDAQ Composite;IXIC;나스닥;나스닥종합;나스닥지수",
    "AAPL": "AAPL;Apple;애플;애플주식",
    "MSFT": "MSFT;Microsoft;마이크로소프트;MS",
    "GOOGL": "GOOGL;Google;Alphabet;구글;알파벳",
    "NVDA": "NVDA;Nvidia;엔비디아",
    "TSLA": "TSLA;Tesla;테슬라",
    "AMZN": "AMZN;Amazon;아마존",
    "META": "META;Facebook;Meta Platforms;메타;페이스북",
    "TLT": "TLT;20+ Year Treasury;미국장기국채;미국채20년",
    "GLD": "GLD;Gold ETF;금ETF;골드",
    "005930": "005930;Samsung Electronics;삼성전자;삼전;삼성",
    "000660": "000660;SK hynix;SK하이닉스;하이닉스;에스케이하이닉스",
    "069500": "069500;KODEX 200;코덱스200;코스피200ETF",
    "KS11": "KS11;KOSPI;코스피;코스피지수;종합주가지수",
    "373220": "373220;LG Energy Solution;LG에너지솔루션;엘지엔솔;LG엔솔",
}

# Minimal metadata so the dev subset is searchable without a full listing fetch.
# (name_en, name_ko, sector, industry, board)
FALLBACK_META = {
    ("AAPL", "US"): ("Apple Inc.", None, "Technology", "Consumer Electronics", "US"),
    ("MSFT", "US"): ("Microsoft Corporation", None, "Technology", "Software", "US"),
    ("KO", "US"): ("Coca-Cola Company", None, "Consumer Defensive", "Beverages", "US"),
    ("005930", "KR"): ("Samsung Electronics", "삼성전자", "IT", "반도체", "KOSPI"),
    ("000660", "KR"): ("SK hynix", "SK하이닉스", "IT", "반도체", "KOSPI"),
}


def classify(ticker: str, market: str) -> tuple[str, bool]:
    """Return (kind, is_tradable) for a curated ticker."""
    if any(t == ticker and m == market for t, m, _, _ in INDICES):
        return "index", False
    if market == "US" and ticker in {*BROAD_ETFS_US, *SECTOR_ETFS_US, *THEME_ETFS_US}:
        return "etf", True
    if market == "KR" and ticker in {code for code, _ in KR_ETFS}:
        return "etf", True
    return "stock", True


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--years", type=int, default=15, help="History depth in years.")
    p.add_argument(
        "--tickers",
        default=None,
        help="Comma-separated TICKER:MARKET pairs. Omit to download the full universe.",
    )
    p.add_argument("--markets", default="KR,US")
    p.add_argument("--kospi", type=int, default=500)
    p.add_argument("--kosdaq", type=int, default=300)
    p.add_argument("--etfs", type=int, default=200)
    p.add_argument("--sleep", type=float, default=0.2, help="Delay between downloads (s).")
    p.add_argument("--force", action="store_true", help="Re-download tickers already cached.")
    return p.parse_args()


def curated_frame(market: str) -> pd.DataFrame:
    """Indices and named ETFs for a market, in bootstrap priority order.

    Priority 1 = indices, 2 = broad index ETFs, 3 = sector / theme / country ETFs.
    """
    rows: list[dict] = []

    def add(ticker: str, name_en: str, name_ko: str | None, board: str) -> None:
        kind, is_tradable = classify(ticker, market)
        rows.append(
            {
                "ticker": ticker,
                "name_en": name_en,
                "name_ko": name_ko,
                "market": market,
                "sector": None,
                "industry": None,
                "board": board,
                "kind": kind,
                "is_tradable": is_tradable,
                "aliases": ALIASES.get(ticker, ""),
            }
        )

    for ticker, mkt, name_en, name_ko in INDICES:          # 1. indices
        if mkt == market:
            add(ticker, name_en, name_ko, "INDEX")

    if market == "US":
        for ticker in BROAD_ETFS_US:                        # 2. broad index ETFs
            add(ticker, ticker, None, "ETF")
        for ticker in [*SECTOR_ETFS_US, *THEME_ETFS_US]:    # 3. sector / theme / country
            add(ticker, ticker, None, "ETF")
    else:
        for code, name_ko in KR_ETFS:                       # 2 + 3 for KR
            add(code, name_ko, name_ko, "ETF")

    return pd.DataFrame(rows)


def build_universe(markets: list[str], args: argparse.Namespace) -> dict[str, pd.DataFrame]:
    """Fetch and persist the ticker metadata table for each market."""
    out: dict[str, pd.DataFrame] = {}
    for market in markets:
        curated = curated_frame(market)
        try:
            listing = fetch_universe(market)
        except Exception as exc:  # noqa: BLE001
            logger.warning("universe listing for %s failed (%s); continuing without it", market, exc)
            data_service.write_tickers(
                curated.assign(
                    first_traded=pd.NaT,
                    last_updated=pd.Timestamp.utcnow().tz_localize(None),
                ),
                market,
            )
            out[market] = curated
            continue

        if market == "KR":
            frames = []
            for board, limit in (("KOSPI", args.kospi), ("KOSDAQ", args.kosdaq)):
                part = listing[listing["board"] == board]
                if "Marcap" in part.columns:
                    part = part.sort_values("Marcap", ascending=False)
                frames.append(part.head(limit))
            constituents = pd.concat(frames, ignore_index=True)   # priority 6, 7
        else:
            stocks = listing[listing["board"] != "ETF"]
            nasdaq = set(NASDAQ_100)
            sp500 = stocks[~stocks["ticker"].isin(nasdaq)].head(500)
            constituents = pd.concat(
                [
                    top_us_etfs(args.etfs),                       # priority 3 (by AUM)
                    sp500,                                        # priority 4
                    stocks[stocks["ticker"].isin(nasdaq)],        # priority 5
                ],
                ignore_index=True,
            )

        constituents = constituents.drop(columns=["Marcap"], errors="ignore")
        if "kind" not in constituents.columns:
            constituents["kind"] = constituents["board"].map(
                lambda b: "etf" if str(b).upper() == "ETF" else "stock"
            )
        constituents["is_tradable"] = True
        constituents["aliases"] = constituents["ticker"].map(lambda t: ALIASES.get(t, ""))

        # Curated rows first so the download loop follows the spec's priority order,
        # and so a curated name/alias wins over a bare listing row for the same ticker.
        listing = pd.concat([curated, constituents], ignore_index=True).drop_duplicates(
            subset=["ticker"], keep="first"
        )
        listing["last_updated"] = pd.Timestamp.utcnow().tz_localize(None)
        listing["first_traded"] = pd.NaT
        data_service.write_tickers(listing, market)
        logger.info(
            "universe %s: %d tickers (%d index, %d etf, %d stock) -> %s",
            market,
            len(listing),
            (listing["kind"] == "index").sum(),
            (listing["kind"] == "etf").sum(),
            (listing["kind"] == "stock").sum(),
            data_service.tickers_file(market),
        )
        out[market] = listing
    return out


def merge_fallback_meta(pairs: list[tuple[str, str]]) -> None:
    """Ensure every requested ticker has a metadata row, even without a listing fetch."""
    curated = {
        (t, m): (en, ko) for t, m, en, ko in INDICES
    }
    curated.update({(code, "KR"): (name, name) for code, name in KR_ETFS})

    by_market: dict[str, list[dict]] = {}
    for ticker, market in pairs:
        meta = FALLBACK_META.get((ticker, market))
        if meta:
            name_en, name_ko, sector, industry, board = meta
        elif (ticker, market) in curated:
            name_en, name_ko = curated[(ticker, market)]
            sector = industry = None
            board = "INDEX" if ticker in {t for t, _, _, _ in INDICES} else "ETF"
        else:
            name_en, name_ko = ticker, None
            sector = industry = None
            board = "KOSPI" if market == "KR" else "US"

        kind, is_tradable = classify(ticker, market)
        by_market.setdefault(market, []).append(
            {
                "ticker": ticker,
                "name_en": name_en,
                "name_ko": name_ko,
                "market": market,
                "sector": sector,
                "industry": industry,
                "board": board,
                "kind": kind,
                "is_tradable": is_tradable,
                "aliases": ALIASES.get(ticker, ""),
                "first_traded": pd.NaT,
                "last_updated": pd.Timestamp.utcnow().tz_localize(None),
            }
        )

    for market, rows in by_market.items():
        new = pd.DataFrame(rows)
        path = data_service.tickers_file(market)
        if path.exists():
            existing = pd.read_parquet(path)
            missing = new[~new["ticker"].isin(existing["ticker"].astype(str))]
            if missing.empty:
                continue
            new = pd.concat([existing, missing], ignore_index=True)
        data_service.write_tickers(new, market)
        logger.info("metadata %s: %d rows", market, len(new))


def resolve_pairs(args: argparse.Namespace, universe: dict[str, pd.DataFrame]) -> list[tuple[str, str]]:
    if args.tickers:
        pairs = []
        for chunk in args.tickers.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            ticker, _, market = chunk.partition(":")
            pairs.append((ticker.strip(), (market or "US").strip().upper()))
        return pairs
    return [
        (str(row.ticker), str(row.market))
        for market, df in universe.items()
        if not df.empty
        for row in df.itertuples()
    ]


def main() -> int:
    args = parse_args()
    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()]
    end = date.today()
    start = end - timedelta(days=int(args.years * 365.25) + 5)

    universe: dict[str, pd.DataFrame] = {}
    if args.tickers:
        merge_fallback_meta(resolve_pairs(args, {}))
    else:
        universe = build_universe(markets, args)

    pairs = resolve_pairs(args, universe)
    logger.info("downloading %d tickers, %s -> %s", len(pairs), start, end)

    ok = skipped = failed = 0
    failures: list[str] = []
    for i, (ticker, market) in enumerate(pairs, 1):
        try:
            data_service.validate(ticker, market)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%d/%d] %s/%s invalid: %s", i, len(pairs), market, ticker, exc)
            failed += 1
            failures.append(f"{market}/{ticker}")
            continue

        path = data_service.ohlcv_file(ticker, market)
        if path.exists() and not args.force:
            skipped += 1
            continue

        try:
            df = fetch_ohlcv(ticker, market, start, end)
        except DataProviderError as exc:
            logger.warning("[%d/%d] %s/%s failed: %s", i, len(pairs), market, ticker, exc)
            failed += 1
            failures.append(f"{market}/{ticker}")
            continue

        data_service.write_ohlcv(df, ticker, market)
        ok += 1
        logger.info(
            "[%d/%d] %s/%s %d rows %s..%s",
            i, len(pairs), market, ticker, len(df),
            df["date"].iloc[0].date(), df["date"].iloc[-1].date(),
        )
        time.sleep(args.sleep)

    logger.info("done: %d downloaded, %d skipped, %d failed", ok, skipped, failed)
    if failures:
        logger.info("failures: %s", ", ".join(failures[:40]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
