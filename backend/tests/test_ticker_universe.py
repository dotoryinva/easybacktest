"""Change 12 — full-universe search, lazy OHLCV loading, and popularity.

These are hermetic: ticker metadata is a hand-built frame and the provider fetch is
stubbed, so nothing here touches the network or the bootstrapped Parquet cache.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import data_providers  # noqa: E402
from app.services import data_service as ds  # noqa: E402

META_COLS = [
    "ticker", "name_en", "name_ko", "market", "sector", "industry",
    "board", "kind", "is_tradable", "aliases",
]


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=META_COLS)


US = _frame([
    {"ticker": "AMZN", "name_en": "Amazon.com, Inc.", "name_ko": None, "market": "US",
     "board": "US", "kind": "stock", "is_tradable": True, "aliases": "AMZN;Amazon;아마존"},
    {"ticker": "AMZP", "name_en": "Kurv Yield Premium Amazon ETF", "name_ko": None,
     "market": "US", "board": "ETF", "kind": "etf", "is_tradable": True, "aliases": ""},
    {"ticker": "^GSPC", "name_en": "S&P 500", "name_ko": "S&P 500 지수", "market": "US",
     "board": "INDEX", "kind": "index", "is_tradable": False, "aliases": "SP500;에스앤피"},
    {"ticker": "TSLA", "name_en": "Tesla, Inc.", "name_ko": None, "market": "US",
     "board": "US", "kind": "stock", "is_tradable": True, "aliases": "테슬라"},
])

KR = _frame([
    {"ticker": "005930", "name_en": "Samsung Electronics", "name_ko": "삼성전자",
     "market": "KR", "board": "KOSPI", "kind": "stock", "is_tradable": True,
     "aliases": "005930;삼성전자;삼전;삼성"},
    {"ticker": "360750", "name_en": None, "name_ko": "TIGER 미국S&P500", "market": "KR",
     "board": "ETF", "kind": "etf", "is_tradable": True, "aliases": ""},
])

UNIVERSE = {"US": US, "KR": KR}


@pytest.fixture
def universe(monkeypatch):
    """Serve the hand-built metadata frames and neutralise the popularity DB."""
    monkeypatch.setattr(ds, "_load_tickers", lambda market: UNIVERSE.get(market, _frame([])))
    monkeypatch.setattr(ds, "popularity_map", lambda market: {})


# --------------------------------------------------------------------------- #
# Search ranking
# --------------------------------------------------------------------------- #


def _codes(results):
    return [t.ticker for t in results]


def test_exact_code_ranks_first(universe):
    assert _codes(ds.search_tickers("AMZN", market="US"))[0] == "AMZN"


def test_name_prefix_beats_name_substring(universe):
    # "amazon" prefixes AMZN's name but only appears mid-name for the AMZP ETF.
    results = _codes(ds.search_tickers("amazon", market="US"))
    assert results[0] == "AMZN"
    assert "AMZP" in results and results.index("AMZN") < results.index("AMZP")


def test_search_spans_the_whole_universe_not_just_cached(universe):
    # None of these have OHLCV files; default cached_only=False must still find them.
    assert _codes(ds.search_tickers("tesla", market="US")) == ["TSLA"]


def test_korean_brand_transliteration_matches_latin_etf_names(universe):
    # 타이거 (phonetic) must reach the Latin-named "TIGER ..." ETF.
    assert "360750" in _codes(ds.search_tickers("타이거", market="KR"))


def test_alias_matches(universe):
    assert _codes(ds.search_tickers("삼전", market="KR")) == ["005930"]


def test_blank_query_returns_nothing(universe):
    assert ds.search_tickers("   ", market="US") == []


# --------------------------------------------------------------------------- #
# Universe membership + lazy loading
# --------------------------------------------------------------------------- #


def test_in_universe(universe):
    assert ds.in_universe("AMZN", "US") is True
    assert ds.in_universe("NOTREAL", "US") is False


def test_ensure_cached_downloads_once_for_a_known_ticker(monkeypatch, tmp_path):
    calls: list[tuple] = []

    def fake_fetch(ticker, market, start, end):
        calls.append((ticker, market))
        return pd.DataFrame({
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "open": [1.0, 1.0], "high": [1.0, 1.0], "low": [1.0, 1.0],
            "close": [1.0, 1.0], "volume": [10.0, 10.0], "adj_close": [1.0, 1.0],
        })

    monkeypatch.setattr(ds, "in_universe", lambda t, m: True)
    monkeypatch.setattr(ds, "ohlcv_file", lambda t, m: tmp_path / f"{t}.parquet")
    monkeypatch.setattr(data_providers, "fetch_ohlcv", fake_fetch)

    assert ds.ensure_cached("AMZN", "US") is True          # first: downloads
    assert (tmp_path / "AMZN.parquet").exists()
    assert ds.ensure_cached("AMZN", "US") is False         # second: already cached
    assert calls == [("AMZN", "US")], "provider hit exactly once"


def test_ensure_cached_refuses_tickers_outside_the_universe(monkeypatch, tmp_path):
    monkeypatch.setattr(ds, "in_universe", lambda t, m: False)
    monkeypatch.setattr(ds, "ohlcv_file", lambda t, m: tmp_path / f"{t}.parquet")
    with pytest.raises(ds.TickerNotFound):
        ds.ensure_cached("NOTREAL", "US")


# --------------------------------------------------------------------------- #
# Popularity
# --------------------------------------------------------------------------- #


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    monkeypatch.setattr(ds.settings, "database_url", f"sqlite:///{tmp_path / 'pop.db'}")
    from app.db import init_db

    init_db()


def test_popularity_roundtrip(temp_db):
    ds.record_query("AAPL", "US")
    ds.record_query("AAPL", "US")
    ds.record_query("MSFT", "US")

    counts = ds.popularity_map("US")
    assert counts["AAPL"] == 2
    assert counts["MSFT"] == 1

    recent = ds.recently_queried(days=1)
    assert ("AAPL", "US") in recent and ("MSFT", "US") in recent


def test_popularity_lifts_a_tie(monkeypatch, temp_db):
    # Two stocks both match "inc" as a name substring; the more-queried one wins.
    frame = _frame([
        {"ticker": "AAA", "name_en": "Alpha Inc", "name_ko": None, "market": "US",
         "board": "US", "kind": "stock", "is_tradable": True, "aliases": ""},
        {"ticker": "BBB", "name_en": "Beta Inc", "name_ko": None, "market": "US",
         "board": "US", "kind": "stock", "is_tradable": True, "aliases": ""},
    ])
    monkeypatch.setattr(ds, "_load_tickers", lambda market: frame if market == "US" else _frame([]))
    for _ in range(5):
        ds.record_query("BBB", "US")

    assert ds.search_tickers("inc", market="US")[0].ticker == "BBB"
