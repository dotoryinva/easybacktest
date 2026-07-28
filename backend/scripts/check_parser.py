#!/usr/bin/env python
"""Live-API check of the Phase 1 "AI Parser Robustness" cases.

Needs a real GEMINI_API_KEY — it makes one API call per case. Everything that can
be verified without the network lives in `tests/test_ai_parser.py` instead.

    python scripts/check_parser.py
    python scripts/check_parser.py --verbose
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import ParsedStrategyResponse, ParseStrategyRequest  # noqa: E402
from app.services import ai_parser  # noqa: E402

# (description, expected_kind, note)
CASES: list[tuple[str, str, str]] = [
    # --- should produce a complete strategy ---
    ("20일 이평선이 60일 이평선을 상향돌파할 때 사고, 하향돌파할 때 팔아", "strategy", ""),
    ("RSI 30 미만에서 사고, RSI 70 이상에서 팔아", "strategy", ""),
    (
        "Buy when the price crosses above the 200-day SMA. Sell when it drops 10% from entry.",
        "strategy",
        "",
    ),
    ("볼린저밴드 하단 터치하면 사고, 5% 익절 3% 손절", "strategy", ""),
    # --- should ask for clarification ---
    ("저평가일 때 사서 오르면 팔아", "clarification", "what defines 저평가?"),
    (
        "골든크로스에서 사고 데드크로스에서 팔아",
        "either",
        "may assume 50/200 and say so in the name, or ask which MAs",
    ),
    ("Buy AAPL when it looks good", "clarification", "no signal defined"),
    ("이평선 돌파할 때 사", "clarification", "which MA? no exit rule"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    try:
        ai_parser.get_client()
    except ai_parser.AIParserUnavailable as exc:
        print(f"SKIP: {exc}")
        return 2

    passed = failed = 0
    for description, expected, note in CASES:
        request = ParseStrategyRequest(
            description=description, ticker="005930", market="KR", conversation_history=[]
        )
        try:
            result = ai_parser.parse_strategy(request)
        except Exception as exc:  # noqa: BLE001 - report, don't abort the sweep
            print(f"✗ ERROR  {description!r}\n         {exc}")
            failed += 1
            continue

        kind = "strategy" if isinstance(result, ParsedStrategyResponse) else "clarification"
        ok = expected == "either" or kind == expected
        mark = "✓" if ok else "✗"
        passed += ok
        failed += not ok

        detail = (
            result.strategy.name
            if isinstance(result, ParsedStrategyResponse)
            else " | ".join(result.questions)
        )
        print(f"{mark} {kind:<13} {description}")
        print(f"  → {detail}")
        if note and (args.verbose or not ok):
            print(f"    (expected {expected}: {note})")
        if args.verbose and isinstance(result, ParsedStrategyResponse):
            for condition in result.strategy.buy_conditions:
                print(f"    BUY  {condition.label()}")
            for condition in result.strategy.sell_conditions:
                print(f"    SELL {condition.label()}")

    print(f"\n{passed} passed, {failed} failed of {len(CASES)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
