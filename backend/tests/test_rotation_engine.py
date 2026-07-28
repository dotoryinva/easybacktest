"""Change 14 동적배분 — rule-based rotation presets, tested hermetically.

Synthetic panels with controlled trends let us assert each rule selects the intended
asset (risk-on vs risk-off, offensive vs defensive) without any network.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backtest import rotation_engine as re  # noqa: E402
from app.schemas import DynamicAllocationRequest  # noqa: E402

DATES = list(pd.bdate_range("2015-01-01", "2020-12-31").date)


def _panel(drift: float) -> pd.DataFrame:
    close = 100.0 * np.power(1.0 + drift, np.arange(len(DATES)))
    return pd.DataFrame({"date": DATES, "adj_open": close * 0.999, "adj_close": close})


def _closes(drifts: dict[str, float]) -> dict[str, pd.Series]:
    out = {}
    for t, d in drifts.items():
        df = _panel(d)
        out[t] = df.set_index(pd.to_datetime(df["date"]).dt.date)["adj_close"]
    return out


DD = date(2018, 6, 15)  # well past the 12-month warmup


# --------------------------------------------------------------------------- #
# Preset selection logic
# --------------------------------------------------------------------------- #


def test_dual_momentum_goes_risk_on_to_the_strongest_equity():
    closes = _closes({"SPY": 0.0008, "VEU": 0.0002, "BND": 0.0, "BIL": 0.00001})
    # SPY strongly up and > BIL, and SPY > VEU ⇒ hold SPY.
    assert re._dual_momentum(closes, DD, 12) == {"SPY": 1.0}


def test_dual_momentum_goes_risk_off_to_bonds_when_equities_lag_cash():
    closes = _closes({"SPY": -0.0005, "VEU": -0.0006, "BND": 0.0, "BIL": 0.0002})
    # SPY 12m return < BIL ⇒ risk-off into BND.
    assert re._dual_momentum(closes, DD, 12) == {"BND": 1.0}


def test_vaa_picks_best_offensive_when_all_healthy():
    closes = _closes({
        "SPY": 0.0009, "VEA": 0.0004, "VWO": 0.0003, "AGG": 0.0001,  # all positive
        "BIL": 0.00001, "IEF": 0.0, "LQD": 0.0,
    })
    picks = re._vaa(closes, DD, 12)
    assert picks == {"SPY": 1.0}, "SPY has the strongest 13612W score"


def test_vaa_flips_defensive_when_an_offensive_asset_is_negative():
    closes = _closes({
        "SPY": -0.0008, "VEA": 0.0004, "VWO": 0.0003, "AGG": 0.0001,  # SPY negative
        "BIL": 0.0001, "IEF": 0.0005, "LQD": 0.0002,
    })
    picks = re._vaa(closes, DD, 12)
    assert set(picks) <= {"BIL", "IEF", "LQD"}
    assert picks == {"IEF": 1.0}, "IEF has the best defensive score"


def test_laa_holds_iwd_in_an_uptrend_and_shy_in_a_downtrend():
    up = re._laa(_closes({"IWD": 0.0004, "GLD": 0.0001, "IEF": 0.0001,
                          "SHY": 0.00001, "SPY": 0.0006}), DD, 12)
    assert up.get("IWD") == 0.25 and up.get("SHY") == 0.25  # timing sleeve = IWD

    down = re._laa(_closes({"IWD": 0.0004, "GLD": 0.0001, "IEF": 0.0001,
                            "SHY": 0.00001, "SPY": -0.0006}), DD, 12)
    assert "IWD" not in down and down.get("SHY") == 0.5  # timing sleeve moved to SHY


def test_gtaa_holds_only_assets_above_their_moving_average():
    closes = _closes({"SPY": 0.0006, "VEA": 0.0004, "VNQ": -0.0006, "DBC": -0.0008, "TLT": 0.0002})
    picks = re._gtaa(closes, DD, 12)
    # Up-trending sleeves are held at 20%; down-trending ones drop to cash.
    assert picks.get("SPY") == 0.2 and picks.get("VEA") == 0.2
    assert "VNQ" not in picks and "DBC" not in picks
    assert sum(picks.values()) < 1.0, "the rest sits in cash"


# --------------------------------------------------------------------------- #
# End-to-end via the engine
# --------------------------------------------------------------------------- #


def test_engine_runs_with_an_injected_loader():
    drifts = {t: 0.0004 for assets in re._ASSETS.values() for t in assets}
    drifts["^GSPC"] = 0.0005
    panels = {t: _panel(d) for t, d in drifts.items()}

    result = re.run_dynamic_allocation(
        DynamicAllocationRequest(
            strategy="dual_momentum",
            start_date=date(2016, 1, 4),
            end_date=date(2020, 12, 30),
            initial_capital=100_000,
        ),
        price_loader=panels.get,
    )
    assert result.equity_curve
    assert result.metrics.num_trades > 0
    assert result.strategy_name == "듀얼 모멘텀 (GEM)"
