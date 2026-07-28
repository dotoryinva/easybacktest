"""`GET /api/seasonality/{market}/{ticker}` — Change 14 Tier 2 계절성.

Hermetic: a synthetic price series with a deliberately planted seasonal pattern (July
strong, September weak) is fed in, and the endpoint must recover that pattern.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import data_service

client = TestClient(app)


@pytest.fixture
def planted(monkeypatch):
    """Daily bars 2015-2024: +0.3%/day in July, -0.2%/day in September, +0.01% otherwise."""
    dates = pd.bdate_range("2015-01-01", "2024-12-31")
    rate = np.where(dates.month == 7, 0.003, np.where(dates.month == 9, -0.002, 0.0001))
    close = 100.0 * np.cumprod(1.0 + rate)
    frame = pd.DataFrame({
        "date": dates, "open": close, "high": close, "low": close,
        "close": close, "volume": np.ones(len(dates)), "adj_close": close,
    })

    def fake_get_ohlcv(ticker, market, start=None, end=None):
        out = frame
        if start is not None:
            out = out[out["date"].dt.date >= start]
        return out.reset_index(drop=True)

    monkeypatch.setattr(data_service, "ensure_cached", lambda t, m, **kw: False)
    monkeypatch.setattr(data_service, "get_ohlcv", fake_get_ohlcv)


def test_recovers_the_planted_monthly_pattern(planted):
    resp = client.get("/api/seasonality/US/TEST")
    assert resp.status_code == 200
    body = resp.json()

    by_month = {m["month"]: m for m in body["month_stats"]}
    assert by_month[7]["mean"] > 0.03, "July was planted strongly positive"
    assert by_month[9]["mean"] < -0.02, "September was planted negative"
    assert by_month[7]["positive_rate"] == 1.0, "every July rises"
    assert by_month[9]["positive_rate"] == 0.0, "every September falls"


def test_shape_of_the_response(planted):
    body = client.get("/api/seasonality/US/TEST").json()
    assert body["ticker"] == "TEST"
    assert body["start_year"] == 2015 and body["end_year"] == 2024
    assert len(body["month_stats"]) == 12
    assert len(body["weekday_stats"]) == 5, "Mon..Fri"
    assert {w["weekday"] for w in body["weekday_stats"]} == {0, 1, 2, 3, 4}
    # ~10 years of month-over-month returns.
    assert 100 <= len(body["monthly"]) <= 130


def test_turn_of_month_partitions_every_trading_day(planted):
    tom = client.get("/api/seasonality/US/TEST").json()["turn_of_month"]
    total = tom["turn_count"] + tom["rest_count"]
    # Every daily return lands in exactly one bucket; ~3 turn days per month.
    assert total > 2000
    assert 0.10 < tom["turn_count"] / total < 0.20


def test_since_filters_the_window(planted):
    body = client.get("/api/seasonality/US/TEST?since=2020").json()
    assert body["start_year"] == 2020


def test_unknown_ticker_is_404(monkeypatch):
    def boom(ticker, market, **kw):
        raise data_service.TickerNotFound("nope")

    monkeypatch.setattr(data_service, "ensure_cached", boom)
    assert client.get("/api/seasonality/US/NOPE").status_code == 404
