"""Indicator primitives — pure `pd.DataFrame -> pd.Series` functions.

Every series is computed on the *adjusted* close so that splits and dividends do not
create phantom signals. Warm-up periods stay NaN; the evaluator drops those bars
rather than back-filling them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..schemas import IndicatorRef

# The price column indicators are derived from. Set once, here, so the choice is
# visible in one place.
PRICE_COL = "adj_close"


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """SMA-seeded exponential moving average.

    Seeding the recursion with the first `period`-bar SMA is what TradingView and the
    other charting packages do; pandas' bare `ewm` seeds with the first observation
    instead, which drifts from the chart the user is looking at. The frontend's
    `utils/indicators.ts` mirrors this implementation.
    """
    values = series.to_numpy(dtype="float64")
    n = values.size
    out = np.full(n, np.nan, dtype="float64")
    if n < period or period < 1:
        return pd.Series(out, index=series.index)

    alpha = 2.0 / (period + 1.0)
    prev = float(np.mean(values[:period]))
    out[period - 1] = prev
    for i in range(period, n):
        prev = alpha * values[i] + (1.0 - alpha) * prev
        out[i] = prev
    return pd.Series(out, index=series.index)


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss
    out = 100 - (100 / (1 + rs))
    # All-gain windows divide by zero -> RSI is 100 by definition.
    out = out.where(avg_loss != 0, 100.0)
    out = out.where(~((avg_loss == 0) & (avg_gain == 0)), 50.0)
    return out


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series]:
    """Returns (macd_line, signal_line)."""
    macd_line = ema(series, fast) - ema(series, slow)
    # The signal line is an EMA of the MACD line, so it starts once MACD has values.
    defined = macd_line.dropna()
    signal_line = pd.Series(np.nan, index=macd_line.index, dtype="float64")
    if not defined.empty:
        signal_line.loc[defined.index] = ema(defined, signal).to_numpy()
    return macd_line, signal_line


def bollinger(
    series: pd.Series, period: int = 20, std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (upper, mid, lower)."""
    mid = sma(series, period)
    # ddof=0 (population sigma) is the standard Bollinger convention.
    sigma = series.rolling(window=period, min_periods=period).std(ddof=0)
    return mid + std * sigma, mid, mid - std * sigma


def resolve(df: pd.DataFrame, ref: IndicatorRef) -> pd.Series:
    """Materialise an `IndicatorRef` against an OHLCV frame."""
    kind, p = ref.kind, ref.params
    price = df[PRICE_COL]

    if kind in ("PRICE_CLOSE", "PRICE_OPEN", "PRICE_HIGH", "PRICE_LOW", "VOLUME"):
        series = {
            "PRICE_CLOSE": price,
            "PRICE_OPEN": df["open"] * _adj_factor(df),
            "PRICE_HIGH": df["high"] * _adj_factor(df),
            "PRICE_LOW": df["low"] * _adj_factor(df),
            "VOLUME": df["volume"].astype(float),
        }[kind]
        # `offset` shifts the series back N bars; the leading N bars become NaN and are
        # treated as warm-up, so they can never produce a signal.
        offset = int(p.get("offset", 0) or 0)
        return series.shift(offset) if offset else series

    if kind == "SMA":
        return sma(price, p["period"])
    if kind == "EMA":
        return ema(price, p["period"])
    if kind == "RSI":
        return rsi(price, p["period"])
    if kind == "MACD_LINE":
        return macd(price, p["fast"], p["slow"], p["signal"])[0]
    if kind == "MACD_SIGNAL":
        return macd(price, p["fast"], p["slow"], p["signal"])[1]
    if kind in ("BOLLINGER_UPPER", "BOLLINGER_MID", "BOLLINGER_LOWER"):
        upper, mid, lower = bollinger(price, p["period"], p["std"])
        return {"BOLLINGER_UPPER": upper, "BOLLINGER_MID": mid, "BOLLINGER_LOWER": lower}[kind]

    if kind == "CONSTANT":
        return pd.Series(float(p["value"]), index=df.index, dtype="float64")

    raise ValueError(f"unsupported indicator kind {kind!r}")


def _adj_factor(df: pd.DataFrame) -> pd.Series:
    """adj_close / close — scales OHL onto the adjusted price scale."""
    return (df["adj_close"] / df["close"]).replace([float("inf")], 1.0).fillna(1.0)


# Approximate close time of each market, in ET hours, so a cross-asset signal is aligned
# without lookahead: KR closes ~01:30 ET (same date), US closes 16:00 ET. A US close on
# date D therefore lands *after* the KR close of date D — so a KR bar can only ever use the
# US close from the day before, which is the D+1 the user expects.
_CLOSE_HOUR_ET = {"KR": 1.5, "US": 16.0}


def _align_to_primary(
    native: pd.Series,
    source_dates: pd.Series,
    source_market: str,
    primary_dates: pd.Series,
    primary_market: str,
    primary_index: pd.Index,
) -> pd.Series:
    """As-of align a source indicator onto the primary calendar by close timestamp.

    Each bar carries its market's close time; for every primary bar we take the most recent
    source value whose close time is <= the primary bar's close time. Never peeks forward.
    """
    src = pd.DataFrame({
        "ts": pd.to_datetime(source_dates).to_numpy()
        + pd.Timedelta(hours=_CLOSE_HOUR_ET.get(source_market, 16.0)),
        "val": native.to_numpy(dtype="float64"),
    }).dropna(subset=["ts"]).sort_values("ts")
    prim = pd.DataFrame({
        "ts": pd.to_datetime(primary_dates).to_numpy()
        + pd.Timedelta(hours=_CLOSE_HOUR_ET.get(primary_market, 16.0)),
        "pos": range(len(primary_dates)),
    }).sort_values("ts")
    merged = pd.merge_asof(prim, src, on="ts", direction="backward").sort_values("pos")
    return pd.Series(merged["val"].to_numpy(), index=primary_index)


def compute_indicators(
    df: pd.DataFrame,
    refs: list[IndicatorRef],
    source_frames: dict[tuple, pd.DataFrame] | None = None,
    primary_market: str = "US",
) -> dict[tuple, pd.Series]:
    """Materialise every distinct ref once. Key is `IndicatorRef.cache_key()`.

    A ref carrying a `ticker` is computed on that source asset's own bars (from
    `source_frames`, keyed by `(ticker, market)`), then as-of aligned onto `df`'s calendar.
    """
    source_frames = source_frames or {}
    out: dict[tuple, pd.Series] = {}
    for ref in refs:
        key = ref.cache_key()
        if key in out:
            continue
        src_key = (ref.ticker, ref.market or primary_market) if ref.ticker else None
        if src_key is not None and src_key in source_frames:
            src_df = source_frames[src_key]
            native = resolve(src_df, ref)
            out[key] = _align_to_primary(
                native, src_df["date"], src_key[1], df["date"], primary_market, df.index
            )
        else:
            out[key] = resolve(df, ref)
    return out


def longest_warmup(refs: list[IndicatorRef]) -> int:
    """Bars of history the slowest indicator needs before it produces a value."""
    warmup = 0
    for ref in refs:
        p = ref.params
        if ref.kind in ("SMA", "EMA", "RSI") or ref.kind.startswith("BOLLINGER"):
            warmup = max(warmup, int(p.get("period", 0)))
        elif ref.kind.startswith("MACD"):
            warmup = max(warmup, int(p.get("slow", 26)) + int(p.get("signal", 9)))
        # A shifted price series needs `offset` bars of history before it has a value.
        warmup = max(warmup, int(p.get("offset", 0) or 0))
    return warmup
