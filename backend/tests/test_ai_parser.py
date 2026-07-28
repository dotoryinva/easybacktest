"""AI parser tests against a stubbed Gemini client.

These cover the parts we own: tool-schema shape, tool dispatch, verbatim description
handling, the schema-repair round-trip, and the clarification round cap. Whether Gemini
picks the *right* tool for a given sentence is a live-API question — see
`scripts/check_parser.py` for that harness.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from google.api_core import exceptions as gexc

from app.schemas import ChatMessage, ClarificationResponse, ParsedStrategyResponse, ParseStrategyRequest
from app.services import ai_parser


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


@dataclass
class FakeFunctionCall:
    name: str
    args: dict


@dataclass
class FakePart:
    function_call: FakeFunctionCall | None = None
    text: str | None = None


@dataclass
class FakeResponse:
    parts: list
    stop_reason: str = "tool_use"


@dataclass
class FakeGenerativeModel:
    responses: list
    calls: list = field(default_factory=list)

    def generate_content(self, contents=None, **kwargs: Any) -> FakeResponse:
        self.calls.append({"contents": contents, **kwargs})
        if not self.responses:
            raise AssertionError("stub client ran out of responses")
        return self.responses.pop(0)


@pytest.fixture
def stub(monkeypatch):
    def install(*responses: FakeResponse) -> FakeGenerativeModel:
        client = FakeGenerativeModel(responses=list(responses))
        monkeypatch.setattr(ai_parser, "get_client", lambda: client)
        return client

    return install


def tool_call(name: str, payload: dict) -> FakeResponse:
    return FakeResponse(parts=[FakePart(function_call=FakeFunctionCall(name=name, args=payload))])


COMPLETE_STRATEGY = {
    "name": "20/60 골든크로스 + 5% 손절",
    "description": "(the model's paraphrase, which should be discarded)",
    "language": "ko",
    "buy_conditions": [
        {
            "left": {"kind": "SMA", "params": {"period": 20}},
            "operator": "cross_above",
            "right": {"kind": "SMA", "params": {"period": 60}},
        }
    ],
    "sell_conditions": [
        {
            "left": {"kind": "SMA", "params": {"period": 20}},
            "operator": "cross_below",
            "right": {"kind": "SMA", "params": {"period": 60}},
        }
    ],
    "stop_loss_pct": 0.05,
}

USER_TEXT = "20일 이평선이 60일 이평선을 상향돌파할 때 사고, 하향돌파할 때 팔아. 5% 손절."


def make_request(description: str = USER_TEXT, history: list[ChatMessage] | None = None):
    return ParseStrategyRequest(
        description=description,
        ticker="005930",
        market="KR",
        conversation_history=history or [],
    )


# --------------------------------------------------------------------------- #
# Tool schema
# --------------------------------------------------------------------------- #


def test_tool_schema_is_self_contained_and_typed():
    schema = ai_parser.CREATE_STRATEGY_TOOL["input_schema"]
    serialized = json.dumps(schema)

    assert "$ref" not in serialized, "refs must be inlined for the tool schema"
    assert "$defs" not in serialized

    assert schema["type"] == "object"
    assert set(schema["required"]) == {"name", "description", "language", "buy_conditions"}

    # `params` must advertise its keys, or the model has nothing to aim at.
    params = schema["properties"]["buy_conditions"]["items"]["properties"]["left"]["properties"][
        "params"
    ]
    assert set(params["properties"]) == {
        "period", "fast", "slow", "signal", "std", "value", "offset",
    }

    kinds = schema["properties"]["buy_conditions"]["items"]["properties"]["left"]["properties"][
        "kind"
    ]["enum"]
    assert "SMA" in kinds and "CONSTANT" in kinds

    # Server-assigned fields must not be in the model's surface.
    assert "id" not in schema["properties"]
    assert "created_at" not in schema["properties"]


def test_both_tools_are_offered_and_a_call_is_forced():
    # Tools + system prompt are baked into the GenerativeModel constructor, not the
    # per-call kwargs, so assert on the static config that get_client() applies.
    assert [t["name"] for t in ai_parser.TOOLS] == ["create_strategy", "ask_clarification"]
    assert "골든크로스" in ai_parser.SYSTEM_PROMPT, "Korean term glossary must reach the model"

    # The schema converter must produce a valid, non-empty Gemini tool for both tools.
    tools = ai_parser._gemini_tools()
    names = {fd.name for fd in tools[0].function_declarations}
    assert names == {"create_strategy", "ask_clarification"}

    # Function calling is forced to ANY (exactly one tool must be called).
    import google.generativeai as genai
    assert (
        ai_parser._TOOL_CONFIG.function_calling_config.mode
        == genai.protos.FunctionCallingConfig.Mode.ANY
    )


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #


def test_create_strategy_returns_a_runnable_strategy(stub):
    stub(tool_call("create_strategy", COMPLETE_STRATEGY))
    result = ai_parser.parse_strategy(make_request())

    assert isinstance(result, ParsedStrategyResponse)
    strategy = result.strategy
    assert strategy.name == "20/60 골든크로스 + 5% 손절"
    assert strategy.stop_loss_pct == 0.05
    assert strategy.buy_conditions[0].left.params["period"] == 20
    assert strategy.id and strategy.created_at, "server assigns id and timestamp"


def test_description_is_the_users_own_words_not_the_models(stub):
    stub(tool_call("create_strategy", COMPLETE_STRATEGY))
    result = ai_parser.parse_strategy(make_request())
    assert result.strategy.description == USER_TEXT


def test_description_uses_the_opening_turn_after_clarification(stub):
    """After a clarification round the original ask is the first user turn."""
    stub(tool_call("create_strategy", COMPLETE_STRATEGY))
    history = [
        ChatMessage(role="user", content=USER_TEXT),
        ChatMessage(role="assistant", content="어떤 이평선인가요?"),
    ]
    result = ai_parser.parse_strategy(make_request("20일과 60일이요", history))
    assert result.strategy.description == USER_TEXT


def test_edit_request_forwards_current_strategy_and_preserves_identity(stub):
    revised = {**COMPLETE_STRATEGY, "name": "20/60 골든크로스 + 3% 손절", "stop_loss_pct": 0.03}
    client = stub(tool_call("create_strategy", revised))
    current = ai_parser._finalize(COMPLETE_STRATEGY, make_request())
    request = make_request("손절을 3%로 바꿔줘")
    request.current_strategy = current

    result = ai_parser.parse_strategy(request)

    assert isinstance(result, ParsedStrategyResponse)
    assert result.strategy.id == current.id
    assert result.strategy.created_at == current.created_at
    assert result.strategy.stop_loss_pct == 0.03
    assert result.strategy.description == current.description
    assert "CURRENT_STRATEGY" in client.calls[0]["contents"][-1]["parts"][0]["text"]


def test_ask_clarification_returns_questions(stub):
    stub(
        tool_call(
            "ask_clarification",
            {
                "questions": ["'저평가'의 기준이 무엇인가요?", "매도 조건은요?"],
                "partial_strategy": None,
            },
        )
    )
    result = ai_parser.parse_strategy(make_request("저평가일 때 사서 오르면 팔아"))

    assert isinstance(result, ClarificationResponse)
    assert len(result.questions) == 2
    assert result.questions[0].startswith("'저평가'")


def test_clarification_questions_are_capped_at_three(stub):
    stub(tool_call("ask_clarification", {"questions": [f"q{i}" for i in range(6)]}))
    result = ai_parser.parse_strategy(make_request("애플 좋아 보이면 사"))
    assert len(result.questions) == 3


def test_conversation_history_is_forwarded_in_order(stub):
    client = stub(tool_call("create_strategy", COMPLETE_STRATEGY))
    history = [
        ChatMessage(role="user", content="이평선 돌파할 때 사"),
        ChatMessage(role="assistant", content="어떤 이평선인가요?"),
    ]
    ai_parser.parse_strategy(make_request("20일과 60일", history))

    # Gemini `contents` carry roles user/model/user (assistant -> model), in order,
    # with the ticker context attached to the final live turn.
    contents = client.calls[0]["contents"]
    assert [c["role"] for c in contents] == ["user", "model", "user"]
    assert contents[0]["parts"][0]["text"] == "이평선 돌파할 때 사"
    assert "005930" in contents[-1]["parts"][0]["text"], "ticker context on the live turn"
    assert contents[-1]["parts"][0]["text"].endswith("20일과 60일")


# --------------------------------------------------------------------------- #
# Repair + guardrails
# --------------------------------------------------------------------------- #


def test_invalid_payload_triggers_one_repair_round(stub):
    """A strategy with no exit rule is rejected; the error goes back to the model."""
    broken = {**COMPLETE_STRATEGY, "sell_conditions": [], "stop_loss_pct": None}
    client = stub(
        tool_call("create_strategy", broken),
        tool_call("create_strategy", COMPLETE_STRATEGY),
    )

    result = ai_parser.parse_strategy(make_request())
    assert isinstance(result, ParsedStrategyResponse)
    assert result.strategy.stop_loss_pct == 0.05
    assert len(client.calls) == 2

    # Verify that a repair round was triggered
    assert len(client.calls) == 2, "Should make two API calls: initial + repair"


def test_repair_may_answer_with_a_clarification(stub):
    broken = {**COMPLETE_STRATEGY, "sell_conditions": [], "stop_loss_pct": None}
    stub(
        tool_call("create_strategy", broken),
        tool_call("ask_clarification", {"questions": ["언제 파실 건가요?"]}),
    )
    result = ai_parser.parse_strategy(make_request())
    assert isinstance(result, ClarificationResponse)
    assert result.questions == ["언제 파실 건가요?"]


def test_two_failed_attempts_degrade_to_a_clarification(stub):
    broken = {**COMPLETE_STRATEGY, "buy_conditions": []}
    stub(tool_call("create_strategy", broken), tool_call("create_strategy", broken))

    result = ai_parser.parse_strategy(make_request())
    assert isinstance(result, ClarificationResponse)
    assert result.partial_strategy is not None, "show the user what was understood"


def test_round_limit_short_circuits_without_calling_the_api(stub):
    client = stub()  # no responses queued: any API call would raise
    history: list[ChatMessage] = []
    for i in range(ai_parser.MAX_CLARIFICATION_ROUNDS):
        history.append(ChatMessage(role="user", content=f"try {i}"))
        history.append(ChatMessage(role="assistant", content=f"question {i}"))

    result = ai_parser.parse_strategy(make_request("여전히 모호함", history))

    assert isinstance(result, ClarificationResponse)
    assert client.calls == []


def test_invalid_api_key_bad_request_is_unavailable(monkeypatch):
    class BadKeyClient:
        def generate_content(self, contents=None, **kwargs: Any) -> FakeResponse:
            raise gexc.InvalidArgument(
                '400 API key not valid. Please pass a valid API key. [reason: "API_KEY_INVALID"]'
            )

    monkeypatch.setattr(ai_parser, "get_client", lambda: BadKeyClient())

    with pytest.raises(ai_parser.AIParserUnavailable, match="Invalid Gemini API key"):
        ai_parser.parse_strategy(make_request())


def test_unavailable_model_error_is_unavailable(monkeypatch):
    class UnavailableModelClient:
        def generate_content(self, contents=None, **kwargs: Any) -> FakeResponse:
            raise gexc.NotFound(
                "404 This model models/gemini-2.5-flash is no longer available to new users."
            )

    monkeypatch.setattr(ai_parser, "get_client", lambda: UnavailableModelClient())

    with pytest.raises(ai_parser.AIParserUnavailable, match="Gemini model"):
        ai_parser.parse_strategy(make_request())


def test_missing_api_key_raises_unavailable(monkeypatch):
    monkeypatch.setattr(ai_parser.settings, "gemini_api_key", "")
    with pytest.raises(ai_parser.AIParserUnavailable):
        ai_parser.get_client()


def test_no_tool_call_is_an_error(stub):
    stub(FakeResponse(parts=[], stop_reason="end_turn"))
    with pytest.raises(ai_parser.AIParserError):
        ai_parser.parse_strategy(make_request())


def test_empty_clarification_questions_are_rejected(stub):
    stub(tool_call("ask_clarification", {"questions": ["  "]}))
    with pytest.raises(ai_parser.AIParserError):
        ai_parser.parse_strategy(make_request())
