"""`POST /api/correlation/matrix` — Change 14 Tier 2.

Hermetic: the OHLCV loader is stubbed with two synthetic series, so the endpoint is
exercised without touching the cache or the network.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.services import data_service

client = TestClient(app)


def _synthetic(monkeypatch, series_by_ticker: dict[str, np.ndarray]) -> None:
    dates = pd.bdate_range("2023-01-01", periods=next(iter(series_by_ticker.values())).size)

    def fake_get_ohlcv(ticker, market, start=None, end=None):
        close = series_by_ticker[ticker]
        return pd.DataFrame({
            "date": dates, "open": close, "high": close, "low": close,
            "close": close, "volume": np.ones_like(close), "adj_close": close,
        })

    monkeypatch.setattr(data_service, "ensure_cached", lambda t, m: False)
    monkeypatch.setattr(data_service, "get_ohlcv", fake_get_ohlcv)


def test_correlation_matrix_shape_and_diagonal(monkeypatch):
    n = 120
    base = np.cumsum(np.random.default_rng(1).normal(0, 1, n)) + 100
    _synthetic(monkeypatch, {"AAA": base, "BBB": base * 1.0 + 0.01})  # near-perfectly correlated

    resp = client.post("/api/correlation/matrix", json={
        "tickers": [{"ticker": "AAA", "market": "US"}, {"ticker": "BBB", "market": "US"}],
        "start_date": "2023-01-01", "end_date": "2023-07-01", "frequency": "daily",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["tickers"] == ["AAA", "BBB"]
    assert body["matrix"][0][0] == 1.0 and body["matrix"][1][1] == 1.0
    assert body["matrix"][0][1] > 0.9, "identical-ish series correlate strongly"
    assert body["matrix"][0][1] == body["matrix"][1][0], "matrix is symmetric"
    assert len(body["stats"]) == 2


def test_correlation_needs_two_series(monkeypatch):
    _synthetic(monkeypatch, {"AAA": np.linspace(100, 110, 60)})

    def only_aaa(ticker, market, start=None, end=None):
        if ticker != "AAA":
            raise data_service.TickerNotFound(ticker)
        n = 60
        dates = pd.bdate_range("2023-01-01", periods=n)
        close = np.linspace(100, 110, n)
        return pd.DataFrame({
            "date": dates, "open": close, "high": close, "low": close,
            "close": close, "volume": np.ones(n), "adj_close": close,
        })

    monkeypatch.setattr(data_service, "get_ohlcv", only_aaa)
    resp = client.post("/api/correlation/matrix", json={
        "tickers": [{"ticker": "AAA", "market": "US"}, {"ticker": "ZZZ", "market": "US"}],
        "start_date": "2023-01-01", "end_date": "2023-04-01", "frequency": "daily",
    })
    assert resp.status_code == 422


def test_correlation_rejects_a_single_ticker():
    resp = client.post("/api/correlation/matrix", json={
        "tickers": [{"ticker": "AAA", "market": "US"}],
        "start_date": "2023-01-01", "end_date": "2023-04-01", "frequency": "daily",
    })
    assert resp.status_code == 422  # min_length=2


def test_cross_market_pairs_are_time_aligned(monkeypatch):
    """A KR asset that mirrors US returns one day late must still correlate ~1.

    Regression for the timezone bug: a KR-listed Nasdaq ETF prices in the *previous* US
    close, so naive same-date matching gave ~0. The close-time alignment must recover it.
    """
    n = 120
    dates = pd.bdate_range("2023-01-02", periods=n)
    rng = np.random.default_rng(7)
    us_ret = rng.normal(0, 0.01, n)
    us_price = 100.0 * np.cumprod(1 + us_ret)
    # KR return on day D equals the US return of day D-1 (the day it was knowable).
    kr_ret = np.concatenate([[0.0], us_ret[:-1]])
    kr_price = 100.0 * np.cumprod(1 + kr_ret)

    def frame(prices):
        return pd.DataFrame({
            "date": dates, "open": prices, "high": prices, "low": prices,
            "close": prices, "volume": np.ones(n), "adj_close": prices,
        })

    frames = {("QQQ", "US"): frame(us_price), ("133690", "KR"): frame(kr_price)}
    monkeypatch.setattr(data_service, "ensure_cached", lambda *a, **k: False)
    monkeypatch.setattr(
        data_service, "get_ohlcv",
        lambda ticker, market, start=None, end=None: frames[(ticker, market)].copy(),
    )

    resp = client.post("/api/correlation/matrix", json={
        "tickers": [{"ticker": "133690", "market": "KR"}, {"ticker": "QQQ", "market": "US"}],
        "start_date": "2023-01-02", "end_date": "2023-06-30", "frequency": "daily",
    })
    assert resp.status_code == 200
    off_diagonal = resp.json()["matrix"][0][1]
    assert off_diagonal > 0.95, f"time-aligned cross-market corr should be ~1, got {off_diagonal}"


def test_cross_market_weekly_and_monthly_returns_align_before_resampling(monkeypatch):
    """D+1 should not turn weekly/monthly trend peers into low-correlation assets."""
    n = 260
    dates = pd.bdate_range("2023-01-02", periods=n)
    rng = np.random.default_rng(11)
    us_ret = rng.normal(0.0005, 0.012, n)
    us_price = 100.0 * np.cumprod(1 + us_ret)
    # A KR-listed Nasdaq ETF embeds the most recent knowable US close: D reflects US D-1.
    kr_price = np.concatenate([[us_price[0]], us_price[:-1]])

    def frame(prices):
        return pd.DataFrame({
            "date": dates, "open": prices, "high": prices, "low": prices,
            "close": prices, "volume": np.ones(n), "adj_close": prices,
        })

    frames = {("QQQ", "US"): frame(us_price), ("133690", "KR"): frame(kr_price)}
    monkeypatch.setattr(data_service, "ensure_cached", lambda *a, **k: False)
    monkeypatch.setattr(
        data_service, "get_ohlcv",
        lambda ticker, market, start=None, end=None: frames[(ticker, market)].copy(),
    )

    for frequency in ("weekly", "monthly"):
        resp = client.post("/api/correlation/matrix", json={
            "tickers": [{"ticker": "133690", "market": "KR"}, {"ticker": "QQQ", "market": "US"}],
            "start_date": "2023-01-02", "end_date": "2023-12-29", "frequency": frequency,
        })
        assert resp.status_code == 200
        off_diagonal = resp.json()["matrix"][0][1]
        assert off_diagonal > 0.95, (
            f"{frequency} D+1-aligned cross-market corr should be ~1, got {off_diagonal}"
        )
