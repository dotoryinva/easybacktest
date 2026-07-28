"""Data-layer tests: ticker validation, filename encoding, metadata columns.

Covers the Phase 1 decision that index symbols keep their leading `^` everywhere except
on disk, where it becomes `_` (`^GSPC` → `_GSPC.parquet`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from app.services import data_service as ds  # noqa: E402


# --------------------------------------------------------------------------- #
# Filename encoding
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("symbol", "stem"),
    [
        ("^GSPC", "_GSPC"),
        ("^IXIC", "_IXIC"),
        ("^VIX", "_VIX"),
        ("AAPL", "AAPL"),
        ("005930", "005930"),
        ("KS11", "KS11"),
    ],
)
def test_filename_encoding_round_trips(symbol: str, stem: str):
    assert ds._encode_filename(symbol) == stem
    assert ds._decode_filename(stem) == symbol


def test_ohlcv_file_uses_the_encoded_stem_but_keeps_the_symbol_canonical():
    path = ds.ohlcv_file("^GSPC", "US")
    assert path.name == "_GSPC.parquet"
    assert path.parent.name == "US"
    # The caret never reaches the filesystem.
    assert "^" not in str(path)


# --------------------------------------------------------------------------- #
# Validation / traversal guard
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("symbol", ["^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX", "KS11", "AAPL"])
def test_index_and_plain_symbols_validate(symbol: str):
    ticker, market = ds.validate(symbol, "US" if symbol.startswith("^") else "KR")
    assert ticker == symbol


@pytest.mark.parametrize(
    "symbol",
    [
        "../etc/passwd",
        "^../x",
        "..",
        "^^GSPC",       # only one leading caret is allowed
        "^",            # caret alone has no symbol body
        "",
        "A" * 20,       # over the length cap
        "AA/BB",
    ],
)
def test_traversal_and_malformed_symbols_are_rejected(symbol: str):
    with pytest.raises(ds.InvalidTicker):
        ds.validate(symbol, "US")


def test_unknown_market_is_rejected():
    with pytest.raises(ds.InvalidTicker):
        ds.validate("AAPL", "JP")


# --------------------------------------------------------------------------- #
# Metadata columns
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    not ds.ohlcv_file("^GSPC", "US").exists(), reason="^GSPC not bootstrapped"
)
def test_index_metadata_marks_it_non_tradable():
    ticker = ds.get_ticker("^GSPC", "US")
    assert ticker.ticker == "^GSPC"
    assert ticker.kind == "index"
    assert ticker.is_tradable is False
    assert "스탠다드앤푸어스" in ticker.aliases


@pytest.mark.skipif(
    not ds.ohlcv_file("005930", "KR").exists(), reason="005930 not bootstrapped"
)
def test_stock_metadata_defaults_to_tradable():
    ticker = ds.get_ticker("005930", "KR")
    assert ticker.kind == "stock"
    assert ticker.is_tradable is True
    assert "삼전" in ticker.aliases


@pytest.mark.skipif(
    not ds.ohlcv_file("^GSPC", "US").exists(), reason="^GSPC not bootstrapped"
)
def test_list_cached_returns_canonical_symbols():
    cached = ds.list_cached("US")
    assert "^GSPC" in cached, "the caret must be restored when listing the cache"
    assert "_GSPC" not in cached


@pytest.mark.skipif(
    not ds.ohlcv_file("^GSPC", "US").exists(), reason="^GSPC not bootstrapped"
)
def test_index_bars_are_readable_by_canonical_symbol():
    df = ds.get_ohlcv("^GSPC", "US")
    assert not df.empty
    assert list(df.columns) == [
        "date", "open", "high", "low", "close", "volume", "adj_close"
    ]


# --------------------------------------------------------------------------- #
# Universe classification
# --------------------------------------------------------------------------- #


def test_classify_assigns_kind_and_tradability():
    from bootstrap_data import classify

    assert classify("^GSPC", "US") == ("index", False)
    assert classify("KS11", "KR") == ("index", False)
    assert classify("SPY", "US") == ("etf", True)
    assert classify("XLK", "US") == ("etf", True)
    assert classify("SOXX", "US") == ("etf", True)
    assert classify("069500", "KR") == ("etf", True)
    assert classify("AAPL", "US") == ("stock", True)
    assert classify("005930", "KR") == ("stock", True)


def test_curated_frame_follows_bootstrap_priority_order():
    from bootstrap_data import curated_frame

    us = curated_frame("US")
    kinds = list(us["kind"])
    # Priority 1 is indices, so every index precedes every ETF.
    last_index = max(i for i, k in enumerate(kinds) if k == "index")
    first_etf = min(i for i, k in enumerate(kinds) if k == "etf")
    assert last_index < first_etf

    tickers = list(us["ticker"])
    assert tickers[:5] == ["^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX"]
    assert tickers[5] == "SPY", "broad index ETFs come before sector/theme ETFs"
    assert tickers.index("SPY") < tickers.index("XLK") < tickers.index("EWZ")

    kr = curated_frame("KR")
    assert list(kr["ticker"])[:4] == ["KS11", "KQ11", "KS200", "KQ150"]
    assert kr[kr["ticker"] == "069500"]["kind"].item() == "etf"


def test_top_20_aliases_are_authored():
    from bootstrap_data import ALIASES

    expected = {
        "SPY", "QQQ", "VOO", "VTI", "^GSPC", "^IXIC", "AAPL", "MSFT", "GOOGL",
        "NVDA", "TSLA", "AMZN", "META", "TLT", "GLD",
        "005930", "000660", "069500", "KS11", "373220",
    }
    assert expected <= set(ALIASES)
    assert all(ALIASES[t].strip() for t in expected)
