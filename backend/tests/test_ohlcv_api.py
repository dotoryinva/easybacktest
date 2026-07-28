"""`/api/ohlcv/{market}/{ticker}` — Lightweight Charts wire format and error handling."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import data_service

client = TestClient(app)

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

has_aapl = pytest.mark.skipif(
    not data_service.ohlcv_file("AAPL", "US").exists(), reason="AAPL not bootstrapped"
)
has_gspc = pytest.mark.skipif(
    not data_service.ohlcv_file("^GSPC", "US").exists(), reason="^GSPC not bootstrapped"
)
has_ks11 = pytest.mark.skipif(
    not data_service.ohlcv_file("KS11", "KR").exists(), reason="KS11 not bootstrapped"
)


@has_aapl
def test_candles_match_the_lightweight_charts_shape():
    response = client.get("/api/ohlcv/US/AAPL", params={"start": "2024-01-02", "end": "2024-01-05"})
    assert response.status_code == 200

    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["market"] == "US"
    assert body["kind"] == "stock"
    assert body["is_tradable"] is True

    candles = body["candles"]
    assert candles, "expected bars in this range"
    for candle in candles:
        # Lightweight Charts accepts a 'YYYY-MM-DD' string for daily series.
        assert ISO_DATE.match(candle["time"])
        assert set(candle) == {"time", "open", "high", "low", "close", "volume"}
        assert candle["low"] <= candle["open"] <= candle["high"]
        assert candle["low"] <= candle["close"] <= candle["high"]
        assert candle["volume"] >= 0

    times = [c["time"] for c in candles]
    assert times == sorted(times), "bars must be ascending for the chart to render"


@has_aapl
def test_date_range_is_inclusive_on_both_ends():
    response = client.get(
        "/api/ohlcv/US/AAPL", params={"start": "2024-01-02", "end": "2024-01-04"}
    )
    times = [c["time"] for c in response.json()["candles"]]
    assert times[0] == "2024-01-02"
    assert times[-1] == "2024-01-04"


@has_aapl
def test_omitting_dates_returns_the_whole_cached_range():
    full = client.get("/api/ohlcv/US/AAPL").json()["candles"]
    windowed = client.get(
        "/api/ohlcv/US/AAPL", params={"start": "2024-01-02", "end": "2024-01-04"}
    ).json()["candles"]
    assert len(full) > len(windowed)


# --------------------------------------------------------------------------- #
# Index symbols — the caret must survive the round trip
# --------------------------------------------------------------------------- #


@has_gspc
@pytest.mark.parametrize("path", ["/api/ohlcv/US/%5EGSPC", "/api/ohlcv/US/^GSPC"])
def test_index_reachable_with_encoded_and_raw_caret(path: str):
    response = client.get(path, params={"start": "2024-01-02", "end": "2024-01-03"})
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "^GSPC", "the API echoes the canonical symbol, not the file stem"
    assert body["kind"] == "index"
    assert body["is_tradable"] is False
    assert body["candles"]


@has_ks11
def test_korean_index_is_served_and_marked_non_tradable():
    body = client.get("/api/ohlcv/KR/KS11").json()
    assert body["ticker"] == "KS11"
    assert body["kind"] == "index"
    assert body["is_tradable"] is False
    assert body["name"] == "코스피"


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


def test_unknown_ticker_is_404_with_an_actionable_message():
    # ZZZZ is not in the universe, so lazy-loading refuses it rather than hitting a
    # provider with arbitrary input.
    response = client.get("/api/ohlcv/US/ZZZZ")
    assert response.status_code == 404
    assert "not in the ticker universe" in response.json()["detail"]


def test_unknown_market_is_rejected():
    assert client.get("/api/ohlcv/JP/AAPL").status_code == 422


@has_aapl
def test_reversed_date_range_is_400():
    response = client.get(
        "/api/ohlcv/US/AAPL", params={"start": "2024-06-01", "end": "2024-01-01"}
    )
    assert response.status_code == 400
    assert "start must not be after end" in response.json()["detail"]


def test_path_traversal_never_reaches_the_handler():
    response = client.get("/api/ohlcv/US/..%2F..%2Fetc%2Fpasswd")
    assert response.status_code in (400, 404)
    assert "passwd" not in response.text
