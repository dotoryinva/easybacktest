"""Manual-mode ↔ AI-mode round-trip gate.

A strategy built in the Manual Builder and the semantically equivalent strategy produced
by the AI parser must run to byte-identical `BacktestResult` objects on the same ticker
and date range. If they ever diverge, the two authoring paths are not interchangeable and
the "a strategy is a strategy regardless of authoring path" guarantee is broken.

The AI side is driven through the real `ai_parser.parse_strategy` with a stubbed
Gemini client, so the tool payload travels the same validation path a live call would.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

from app.backtest.engine import run_backtest
from app.schemas import BacktestParams, ParseStrategyRequest, Strategy
from app.services import ai_parser, data_service

from test_ai_parser import FakeGenerativeModel, tool_call

PARAMS = BacktestParams(
    ticker="AAPL",
    market="US",
    start_date=dt.date(2022, 1, 1),
    end_date=dt.date(2026, 1, 1),
    initial_capital=10_000,
)

# The 골든크로스 (50/200) preset exactly as `frontend/src/utils/presets.ts` emits it.
GOLDEN_CROSS_PRESET = {
    "name": "골든크로스 (50/200)",
    "description": "50일 이평선이 200일 이평선을 상향돌파하면 매수, 하향돌파하면 매도합니다.",
    "language": "ko",
    "buy_conditions": [
        {
            "left": {"kind": "SMA", "params": {"period": 50}},
            "operator": "cross_above",
            "right": {"kind": "SMA", "params": {"period": 200}},
        }
    ],
    "sell_conditions": [
        {
            "left": {"kind": "SMA", "params": {"period": 50}},
            "operator": "cross_below",
            "right": {"kind": "SMA", "params": {"period": 200}},
        }
    ],
    "stop_loss_pct": None,
    "take_profit_pct": None,
    "max_holding_days": None,
    "position_sizing": "all_in",
    "position_size_value": None,
    "allow_reentry_same_day": False,
    "cooldown_days_after_exit": 0,
}

needs_aapl = pytest.mark.skipif(
    not data_service.ohlcv_file("AAPL", "US").exists(), reason="AAPL not bootstrapped"
)


def comparable(result) -> str:
    """Serialise a BacktestResult minus the fields that differ by construction."""
    payload = result.model_dump(mode="json")
    payload.pop("ran_at")          # wall clock
    payload.pop("strategy_id")     # ULID, assigned per authoring path
    payload.pop("strategy_name")   # user-facing label, not part of the computation
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def parse_via_ai(monkeypatch, payload: dict) -> Strategy:
    """Run the real parser against a stubbed model that emits `payload`."""
    client = FakeGenerativeModel(responses=[tool_call("create_strategy", payload)])
    monkeypatch.setattr(ai_parser, "get_client", lambda: client)

    response = ai_parser.parse_strategy(
        ParseStrategyRequest(
            description="50일 이평선이 200일 이평선을 상향돌파하면 사고, 하향돌파하면 팔아",
            ticker="AAPL",
            market="US",
            conversation_history=[],
        )
    )
    assert response.kind == "strategy"
    return response.strategy


@needs_aapl
def test_manual_and_ai_strategies_produce_identical_results(monkeypatch):
    # Manual mode: the preset object goes straight into Strategy.
    manual = Strategy.model_validate(GOLDEN_CROSS_PRESET)
    # AI mode: the same semantics arrive as a create_strategy tool payload.
    ai = parse_via_ai(monkeypatch, GOLDEN_CROSS_PRESET)

    assert manual.id != ai.id, "each path assigns its own id"

    manual_result = run_backtest(manual, PARAMS)
    ai_result = run_backtest(ai, PARAMS)

    assert comparable(manual_result) == comparable(ai_result)
    assert manual_result.metrics.num_trades > 0, "a no-trade run would prove nothing"


@needs_aapl
def test_roundtrip_holds_for_a_strategy_with_every_exit_rule(monkeypatch):
    """Exit rules, sizing and reentry policy must survive both paths too."""
    payload = {
        **GOLDEN_CROSS_PRESET,
        "name": "전체 청산 규칙",
        "stop_loss_pct": 0.05,
        "take_profit_pct": 0.15,
        "max_holding_days": 30,
        "position_sizing": "percent_of_capital",
        "position_size_value": 0.5,
        "cooldown_days_after_exit": 3,
    }
    manual = Strategy.model_validate(payload)
    ai = parse_via_ai(monkeypatch, payload)

    assert comparable(run_backtest(manual, PARAMS)) == comparable(run_backtest(ai, PARAMS))


@needs_aapl
def test_roundtrip_holds_for_the_offset_preset(monkeypatch):
    """듀얼 모멘텀 uses `offset`, the newest param — verify it survives the AI path."""
    payload = {
        "name": "듀얼 모멘텀 (단일종목판)",
        "description": "종가가 200일선 위이고 1년 전보다 높으면 매수",
        "language": "ko",
        "buy_conditions": [
            {
                "left": {"kind": "PRICE_CLOSE", "params": {}},
                "operator": ">",
                "right": {"kind": "SMA", "params": {"period": 200}},
            },
            {
                "left": {"kind": "PRICE_CLOSE", "params": {}},
                "operator": ">",
                "right": {"kind": "PRICE_CLOSE", "params": {"offset": 252}},
            },
        ],
        "sell_conditions": [
            {
                "left": {"kind": "PRICE_CLOSE", "params": {}},
                "operator": "<",
                "right": {"kind": "SMA", "params": {"period": 200}},
            }
        ],
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "max_holding_days": None,
        "position_sizing": "all_in",
        "position_size_value": None,
        "allow_reentry_same_day": False,
        "cooldown_days_after_exit": 0,
    }
    manual = Strategy.model_validate(payload)
    ai = parse_via_ai(monkeypatch, payload)

    assert manual.buy_conditions[1].right.params["offset"] == 252
    assert ai.buy_conditions[1].right.params["offset"] == 252
    assert comparable(run_backtest(manual, PARAMS)) == comparable(run_backtest(ai, PARAMS))
