#!/usr/bin/env python
"""Incremental OHLCV update — pulls the last N trading days and upserts.

Runs nightly at 07:00 KST via APScheduler (see app/main.py), and is safe to invoke by
hand. Weekend runs are a no-op.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_providers import DataProviderError, fetch_ohlcv  # noqa: E402
from app.services import data_service  # noqa: E402

logger = logging.getLogger("nightly_refresh")

KST = ZoneInfo("Asia/Seoul")


def refresh(
    lookback_days: int = 5,
    markets: tuple[str, ...] = ("KR", "US"),
    sleep: float = 0.15,
    force: bool = False,
) -> dict[str, int]:
    """Refresh every cached ticker. Returns {'updated': n, 'failed': n, 'skipped': n}."""
    now_kst = datetime.now(KST)
    if now_kst.weekday() >= 5 and not force:
        logger.info("weekend in KST (%s) — nothing to refresh", now_kst.date())
        return {"updated": 0, "failed": 0, "skipped": 0}

    end = date.today()
    # Calendar days that comfortably cover `lookback_days` trading days.
    start = end - timedelta(days=lookback_days * 2 + 5)

    stats = {"updated": 0, "failed": 0, "skipped": 0}
    for market in markets:
        tickers = data_service.list_cached(market)
        logger.info("refreshing %d %s tickers (%s..%s)", len(tickers), market, start, end)
        for ticker in tickers:
            try:
                df = fetch_ohlcv(ticker, market, start, end)
            except DataProviderError as exc:
                logger.warning("%s/%s refresh failed: %s", market, ticker, exc)
                stats["failed"] += 1
                continue
            if df.empty:
                stats["skipped"] += 1
                continue
            rows = data_service.upsert_ohlcv(df, ticker, market)
            stats["updated"] += 1
            logger.debug("%s/%s -> %d rows", market, ticker, rows)
            time.sleep(sleep)

    logger.info("refresh done: %s", stats)
    return stats


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", stream=sys.stdout
    )
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lookback-days", type=int, default=5)
    p.add_argument("--markets", default="KR,US")
    p.add_argument("--force", action="store_true", help="Run even on a KST weekend.")
    args = p.parse_args()

    markets = tuple(m.strip().upper() for m in args.markets.split(",") if m.strip())
    refresh(lookback_days=args.lookback_days, markets=markets, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
