import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import data_service  # noqa: E402


def make_frame(rows: list[dict]) -> pd.DataFrame:
    """Build a canonical OHLCV frame from `{date, open, high, low, close}` dicts."""
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    if "volume" not in df:
        df["volume"] = 1_000_000.0
    if "adj_close" not in df:
        df["adj_close"] = df["close"]
    return df[["date", "open", "high", "low", "close", "volume", "adj_close"]]


@pytest.fixture
def synthetic(monkeypatch):
    """Serve a hand-built frame in place of the Parquet cache."""

    def install(rows: list[dict], board: str | None = "US"):
        frame = make_frame(rows)

        def fake_get_ohlcv(ticker, market, start=None, end=None):
            out = frame.copy()
            if start is not None:
                out = out[out["date"].dt.date >= start]
            if end is not None:
                out = out[out["date"].dt.date <= end]
            return out.reset_index(drop=True)

        monkeypatch.setattr(data_service, "get_ohlcv", fake_get_ohlcv)
        monkeypatch.setattr(data_service, "board_of", lambda t, m: board)
        return frame

    return install


@pytest.fixture(scope="session")
def has_aapl() -> bool:
    return data_service.ohlcv_file("AAPL", "US").exists()


@pytest.fixture(scope="session")
def has_samsung() -> bool:
    return data_service.ohlcv_file("005930", "KR").exists()
