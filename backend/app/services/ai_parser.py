"""Natural language -> executable Strategy, via Gemini tool use.

Gemini is forced to call exactly one of two tools:
`create_strategy` when the description is complete, `ask_clarification` when it is not.

Thinking is deliberately left off: the parse has to land inside the 5-second budget the
Phase 1 success criteria set, and the task is closer to structured extraction than to
reasoning. Raise `effort`/enable adaptive thinking here if parse quality ever needs it.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import google.generativeai as genai
from google.api_core import exceptions as gexc
from pydantic import ValidationError

from ..config import settings
from ..schemas import (
    ChatMessage,
    ClarificationResponse,
    ParsedStrategyResponse,
    ParseStrategyRequest,
    Strategy,
    StrategyDraft,
)

logger = logging.getLogger(__name__)

MAX_CLARIFICATION_ROUNDS = 3
MAX_TOKENS = 4096


class AIParserError(RuntimeError):
    """The parser could not produce a usable result."""


class AIParserUnavailable(AIParserError):
    """No API key configured, or the upstream API is unreachable."""


def _is_invalid_api_key_error(exc: BaseException) -> bool:
    """Google sometimes reports invalid Gemini keys as a 400 BadRequest."""
    message = str(exc)
    return "API_KEY_INVALID" in message or "API key not valid" in message


def _is_unavailable_model_error(exc: BaseException) -> bool:
    message = str(exc)
    return (
        "no longer available to new users" in message
        or "model is not found" in message.lower()
        or "models/" in message and "is not found" in message
    )


# --------------------------------------------------------------------------- #
# Tool schemas
# --------------------------------------------------------------------------- #


def _inline_refs(schema: dict) -> dict:
    """Resolve `$ref`/`$defs` into a self-contained schema.

    Pydantic emits `$defs` + `$ref`; inlining keeps the tool schema portable and
    removes a class of subtle mismatches in how references are interpreted.
    Also strips keys not supported by Gemini's strict OpenAPI subset.
    """
    defs = schema.get("$defs", {})
    UNSUPPORTED_KEYS = {
        "minItems", "maxItems", "title", "default", "$defs", "anyOf",
        "additionalProperties", "exclusiveMaximum", "exclusiveMinimum",
        "minimum", "maximum", "pattern", "minLength", "maxLength"
    }

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            # Convert type arrays like ["object", "null"] into type + nullable
            if "type" in node and isinstance(node["type"], list):
                types = node["type"]
                non_null_types = [t for t in types if t != "null"]
                node["type"] = non_null_types[0] if non_null_types else "object"
                if "null" in types:
                    node["nullable"] = True

            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                target = defs.get(ref.split("/")[-1], {})
                merged = {**walk(target), **{k: v for k, v in node.items() if k != "$ref" and k not in UNSUPPORTED_KEYS}}
                return merged
            
            # Handle anyOf with null
            if "anyOf" in node:
                any_of = node["anyOf"]
                non_null = [item for item in any_of if item.get("type") != "null"]
                if len(non_null) == 1:
                    base = walk(non_null[0])
                    base["nullable"] = True
                    return {k: v for k, v in base.items() if k not in UNSUPPORTED_KEYS}

            return {k: walk(v) for k, v in node.items() if k not in UNSUPPORTED_KEYS}
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    return walk(schema)


CREATE_STRATEGY_TOOL: dict = {
    "name": "create_strategy",
    "description": (
        "Emit a complete, executable trading strategy when the user's description "
        "contains all necessary information."
    ),
    "input_schema": _inline_refs(StrategyDraft.model_json_schema()),
}

ASK_CLARIFICATION_TOOL: dict = {
    "name": "ask_clarification",
    "description": (
        "Ask 1-3 focused clarifying questions when the description is missing "
        "critical information."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Questions, written in the user's own language.",
            },
            "partial_strategy": {
                "type": "object",
                "nullable": True,
                "description": (
                    "The best-effort partial strategy so the frontend can show what has "
                    "been understood so far. Omit or null if nothing is settled yet."
                ),
            },
        },
        "required": ["questions"],
    },
}

TOOLS = [CREATE_STRATEGY_TOOL, ASK_CLARIFICATION_TOOL]


SYSTEM_PROMPT = """\
You are a trading strategy parser. You convert natural language descriptions of stock \
trading strategies into structured, executable strategy definitions.

You have two tools. You MUST use exactly one of them:

1. `create_strategy` — Use this when the user's description contains all the information \
needed to run a backtest.
2. `ask_clarification` — Use this when critical information is missing. Ask 1 to 3 \
focused questions.

If the user provides a CURRENT_STRATEGY block, treat the user's message as an edit request:
- Start from CURRENT_STRATEGY and change only what the user asked to change.
- Return a complete revised strategy, not a patch.
- Preserve the existing description unless the user explicitly asks to rewrite it.
- If the requested edit is ambiguous, ask focused clarification questions.

"Complete" means all of the following:
- At least one buy condition with specific indicators and thresholds
- Either at least one sell condition, or a stop_loss_pct, or a take_profit_pct (any exit \
rule is fine)
- Buy/sell conditions reference specific periods (e.g., "20-day SMA", not just "moving \
average")

"Ambiguous" examples that require clarification:
- "Buy when the stock is cheap" → ask what "cheap" means (RSI < 30? P/E ratio? % off \
52-week high?)
- "Buy on the golden cross" → ask which two moving averages (5/20? 20/60? 50/200?)
- "Buy when it's going up" → ask what specific signal indicates uptrend
- Buy conditions specified but NO exit rule at all → ask for either sell conditions or a \
stop loss

Defaults you SHOULD assume without asking:
- Position sizing: "all_in" if not mentioned
- Fee rate and tax rate: null (backend will fill market defaults)
- Slippage: 0.1%
- Reentry: allow_reentry_same_day=false, cooldown_days_after_exit=0
- Moving average price basis: closing price
- RSI period: 14
- MACD parameters: 12/26/9
- Bollinger Bands: 20-period, 2 standard deviations

Language:
- Detect the user's language from their description
- Ask clarification questions in the SAME language
- The Strategy's `name` field: generate a short, descriptive name in the user's language \
(e.g., "20/60 골든크로스 + 5% 손절" or "RSI Oversold Bounce")
- The Strategy's `description` field: copy the user's original description verbatim

Common Korean trading terms to recognize:
- "골든크로스" = shorter MA crosses above longer MA
- "데드크로스" = shorter MA crosses below longer MA
- "이평선" or "이동평균선" = moving average (usually SMA unless specified)
- "손절" = stop loss
- "익절" = take profit
- "돌파" = cross above (breakout)
- "이탈" = cross below (breakdown)
- "과매수/과매도" = overbought/oversold (typically RSI > 70 / RSI < 30)

Common English terms:
- "Golden cross" / "death cross"
- "Cross above" / "cross below"
- "Stop loss" / "take profit" / "trailing stop"

Never invent numbers the user didn't specify. If the user says "moving average" without a \
period, ASK. Do not default to a period unless it's a well-known named pattern (e.g., \
"golden cross" without periods commonly means 50/200 SMA — you may assume this default and \
MENTION your assumption in the strategy name).

Never emit a strategy with zero buy conditions.
Never emit a strategy with zero exit rules (no sell conditions AND no stop_loss AND no \
take_profit).

## Condition encoding

Every condition is `{left, operator, right}` where each side is an indicator reference:
`{"kind": ..., "params": {...}}`. Compare against a literal number using
`{"kind": "CONSTANT", "params": {"value": 30}}`.

## Worked examples

Example 1 — Korean, complete.
User: "삼성전자 20일 이평선이 60일 이평선을 상향돌파할 때 사고, 하향돌파할 때 팔아. 5% 손절도 걸어줘."
Call `create_strategy` with:
  name: "20/60 골든크로스 + 5% 손절"
  language: "ko"
  buy_conditions: [{left: SMA(period 20), operator: "cross_above", right: SMA(period 60)}]
  sell_conditions: [{left: SMA(period 20), operator: "cross_below", right: SMA(period 60)}]
  stop_loss_pct: 0.05

Example 2 — English, ambiguous.
User: "Buy Apple when it's oversold and sell when it recovers."
Call `ask_clarification` with questions:
  - "What indicator defines 'oversold'? Common options are RSI (e.g., RSI < 30) or price \
% below a moving average."
  - "What defines 'recovery' — a specific RSI level like 50, or crossing back above a \
moving average?"

Example 3 — Korean, mixed.
User: "RSI가 30 밑으로 갔다가 다시 30 위로 올라올 때 사고, 10% 오르거나 3% 내리면 팔아"
Call `create_strategy` with:
  name: "RSI 30 반등 매수, 10%/-3% 청산"
  language: "ko"
  buy_conditions: [{left: RSI(period 14), operator: "cross_above", right: CONSTANT 30}]
  take_profit_pct: 0.10
  stop_loss_pct: 0.03
  (interpret "밑으로 갔다가 다시 위로" as cross_above)
"""


# --------------------------------------------------------------------------- #
# Gemini schema + tool construction
# --------------------------------------------------------------------------- #

RETRY_DELAYS = (1.0, 2.0, 4.0)  # exponential backoff on transient rate limits

_JSON_TO_GEMINI_TYPE = {
    "object": "OBJECT",
    "array": "ARRAY",
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
}


def _to_gemini_schema(node: Any) -> dict:
    """Convert an (already ref-inlined) JSON Schema into Gemini's Schema subset.

    Our tool schemas carry no `$ref`/`anyOf`/null-unions (see `_inline_refs`), so a
    straight structural walk suffices: map JSON type names to Gemini's uppercase enum
    and carry over description/enum/properties/items/required. Object nodes with no
    representable properties (Gemini rejects a propertyless OBJECT) are dropped by
    returning `{}`, which the parent then skips.
    """
    if not isinstance(node, dict):
        return {}
    out: dict = {}
    t = node.get("type")
    if isinstance(t, list):  # tolerate ["object", "null"] just in case
        t = next((x for x in t if x != "null"), None)
    if isinstance(t, str) and t.lower() in _JSON_TO_GEMINI_TYPE:
        out["type"] = _JSON_TO_GEMINI_TYPE[t.lower()]
    if node.get("description"):
        out["description"] = node["description"]
    if "enum" in node:
        out["enum"] = [str(e) for e in node["enum"]]
        out.setdefault("type", "STRING")
    if "properties" in node:
        props = {}
        for key, value in node["properties"].items():
            converted = _to_gemini_schema(value)
            if converted:
                props[key] = converted
        if props:
            out["type"] = "OBJECT"
            out["properties"] = props
            required = [r for r in node.get("required", []) if r in props]
            if required:
                out["required"] = required
    if "items" in node:
        items = _to_gemini_schema(node["items"])
        if items:
            out["type"] = "ARRAY"
            out["items"] = items
    if out.get("type") == "OBJECT" and "properties" not in out:
        return {}  # unrepresentable freeform object — parent skips it
    return out


def _gemini_tools() -> list:
    """The two forced tools, as Gemini FunctionDeclarations."""
    declarations = [
        genai.protos.FunctionDeclaration(
            name=tool["name"],
            description=tool["description"],
            parameters=_to_gemini_schema(tool["input_schema"]),
        )
        for tool in TOOLS
    ]
    return [genai.protos.Tool(function_declarations=declarations)]


_TOOL_CONFIG = genai.protos.ToolConfig(
    function_calling_config=genai.protos.FunctionCallingConfig(
        mode=genai.protos.FunctionCallingConfig.Mode.ANY  # force exactly one tool call
    )
)
_GENERATION_CONFIG = {"temperature": 0.0, "max_output_tokens": MAX_TOKENS}


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #

def get_client() -> genai.GenerativeModel:
    if not settings.gemini_api_key:
        raise AIParserUnavailable(
            "GEMINI_API_KEY is not set — the AI strategy builder is disabled."
        )
    genai.configure(api_key=settings.gemini_api_key)
    return genai.GenerativeModel(
        settings.active_model,
        system_instruction=SYSTEM_PROMPT,
        tools=_gemini_tools(),
        tool_config=_TOOL_CONFIG,
        generation_config=_GENERATION_CONFIG,
    )


def _build_messages(request: ParseStrategyRequest) -> list[dict]:
    """Conversation history plus the current turn, framed with the ticker context."""
    messages: list[dict] = []
    for turn in request.conversation_history:
        messages.append({"role": turn.role, "content": turn.content})

    current = ""
    if request.current_strategy is not None:
        current = (
            "[CURRENT_STRATEGY]\n"
            f"{request.current_strategy.model_dump_json(exclude={'id', 'created_at'})}\n"
            "[/CURRENT_STRATEGY]\n\n"
        )
    header = (
        f"[Context] The user is building a strategy for {request.market}/{request.ticker}. "
        f"Single ticker, daily bars.\n\n"
    )
    messages.append({"role": "user", "content": header + current + request.description})

    # The API requires the first message to be from the user.
    if messages[0]["role"] != "user":
        messages.insert(0, {"role": "user", "content": request.description})
    return messages


def _original_description(request: ParseStrategyRequest) -> str:
    """The user's first message — what belongs in Strategy.description, verbatim."""
    if request.current_strategy is not None:
        return request.current_strategy.description
    for turn in request.conversation_history:
        if turn.role == "user":
            return turn.content
    return request.description


def _to_contents(msgs: list[dict]) -> list[dict]:
    """Map our {role, content} messages onto Gemini `contents` (roles: user/model)."""
    return [
        {
            "role": "model" if m["role"] == "assistant" else "user",
            "parts": [{"text": m["content"]}],
        }
        for m in msgs
    ]


def _function_args(fc) -> dict:
    """Deep-convert a Gemini FunctionCall's args into a plain dict.

    Real protos expose the classmethod `to_dict` (which recurses into nested structs);
    the test doubles hand back a plain dict directly.
    """
    to_dict = getattr(type(fc), "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict(fc).get("args", {}) or {}
        except Exception:  # noqa: BLE001 - fall back to shallow access
            pass
    args = getattr(fc, "args", {}) or {}
    return args if isinstance(args, dict) else dict(args)


def _extract_tool_call(response) -> tuple[str, dict]:
    parts = getattr(response, "parts", None)
    if parts is None:
        try:
            parts = response.candidates[0].content.parts
        except (AttributeError, IndexError):
            parts = []
    for part in parts:
        fc = getattr(part, "function_call", None)
        if fc is None:
            continue
        name = getattr(fc, "name", "") or ""
        if not name:
            continue
        return name, _function_args(fc)
    raise AIParserError("model returned no tool call")


def parse_strategy(
    request: ParseStrategyRequest,
) -> ParsedStrategyResponse | ClarificationResponse:
    client = get_client()
    messages = _build_messages(request)

    rounds_used = sum(1 for m in request.conversation_history if m.role == "assistant")
    if rounds_used >= MAX_CLARIFICATION_ROUNDS:
        return ClarificationResponse(
            questions=[
                "3번의 확인 질문 후에도 전략이 명확하지 않습니다. 매수 조건과 매도 조건을 "
                "지표와 기간을 포함해 한 문장씩으로 다시 적어주세요. "
                "(예: 'RSI(14)가 30 아래로 내려가면 매수, 70 위로 올라가면 매도')",
                "Still ambiguous after 3 rounds. Please restate the entry and exit rules "
                "as one sentence each, naming the indicator and its period — e.g. "
                "'Buy when RSI(14) crosses below 30, sell when it crosses above 70.'",
            ],
            partial_strategy=None,
        )

    def call(msgs: list[dict]):
        contents = _to_contents(msgs)
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                return client.generate_content(contents)
            except (gexc.PermissionDenied, gexc.Unauthenticated) as exc:
                # Invalid or revoked API key — no point retrying.
                raise AIParserUnavailable(
                    "GEMINI_API_KEY가 유효하지 않습니다. .env 파일의 키를 확인해주세요. "
                    "(Invalid Gemini API key — check your .env file.)"
                ) from exc
            except (gexc.ResourceExhausted, gexc.ServiceUnavailable) as exc:
                # Transient: rate limit / capacity. Back off and retry, then give up.
                if attempt < len(RETRY_DELAYS):
                    time.sleep(RETRY_DELAYS[attempt])
                    continue
                kind = (
                    "rate limit or quota exceeded"
                    if isinstance(exc, gexc.ResourceExhausted)
                    else "temporarily unavailable"
                )
                raise AIParserUnavailable(
                    f"Gemini API {kind} — 잠시 후 다시 시도해주세요."
                ) from exc
            except gexc.GoogleAPICallError as exc:
                # A definite API-side error (bad request, auth, etc.) — no point retrying.
                if _is_invalid_api_key_error(exc):
                    raise AIParserUnavailable(
                        "GEMINI_API_KEY가 유효하지 않습니다. .env 파일의 키를 확인해주세요. "
                        "(Invalid Gemini API key — check your .env file.)"
                    ) from exc
                if _is_unavailable_model_error(exc):
                    raise AIParserUnavailable(
                        f"Gemini model {settings.active_model!r} is unavailable. "
                        "Update GEMINI_MODEL in your .env file."
                    ) from exc
                raise AIParserError(f"Gemini API error: {exc}") from exc
            except gexc.GoogleAPIError as exc:
                raise AIParserUnavailable(f"could not reach the Gemini API: {exc}") from exc
        raise AIParserUnavailable(  # pragma: no cover - loop returns or raises above
            "could not reach the Gemini API"
        )

    response = call(messages)
    name, payload = _extract_tool_call(response)

    if name == "ask_clarification":
        questions = [q for q in payload.get("questions", []) if str(q).strip()]
        if not questions:
            raise AIParserError("ask_clarification returned no questions")
        return ClarificationResponse(
            questions=questions[:3], partial_strategy=payload.get("partial_strategy")
        )

    if name != "create_strategy":
        raise AIParserError(f"unexpected tool {name!r}")

    try:
        strategy = _finalize(payload, request)
    except ValidationError as first_error:
        logger.info("create_strategy failed validation, asking the model to repair: %s", first_error)
        repaired = _repair(call, messages, response, first_error, request)
        if repaired is not None:
            return repaired
        # Repair failed too — a clarification beats surfacing a schema error.
        return ClarificationResponse(
            questions=[
                "전략을 실행 가능한 형태로 변환하지 못했습니다. 매수 조건과 매도(청산) 조건을 "
                "지표 이름과 기간을 포함해 더 구체적으로 알려주세요.",
                "I couldn't turn that into an executable strategy. Please restate the entry "
                "and exit rules, naming each indicator and its period.",
            ],
            partial_strategy=payload,
        )

    return ParsedStrategyResponse(strategy=strategy)


def _finalize(payload: dict, request: ParseStrategyRequest) -> Strategy:
    """Validate the tool payload and pin `description` to the user's own words."""
    draft = StrategyDraft.model_validate(payload)
    if request.current_strategy is not None:
        # Editing an existing strategy: keep its identity and original description; only the
        # revised fields (conditions, stops, …) come from the model's payload.
        return Strategy(
            **draft.model_dump(exclude={"description"}),
            description=_original_description(request),
            id=request.current_strategy.id,
            created_at=request.current_strategy.created_at,
        )
    return Strategy(
        **draft.model_dump(exclude={"description"}),
        description=_original_description(request),
    )


def _repair(
    call, messages: list[dict], response, error: ValidationError, request: ParseStrategyRequest
):
    """One corrective round-trip: hand the validation error back to the model."""
    # Convert the Gemini response to text format for error feedback
    error_text = (
        "The strategy failed schema validation:\n"
        f"{json.dumps(error.errors(include_url=False), default=str, ensure_ascii=False)}\n"
        "Fix these fields and call the tool again, or call "
        "`ask_clarification` if the description genuinely lacks the "
        "information needed."
    )

    repair_messages = [
        *messages,
        {"role": "assistant", "content": json.dumps({"error": "validation_failed", "message": error_text})},
        {
            "role": "user",
            "content": error_text,
        },
    ]

    retry = call(repair_messages)
    name, payload = _extract_tool_call(retry)

    if name == "ask_clarification":
        questions = [q for q in payload.get("questions", []) if str(q).strip()]
        if questions:
            return ClarificationResponse(
                questions=questions[:3], partial_strategy=payload.get("partial_strategy")
            )
        return None

    try:
        return ParsedStrategyResponse(strategy=_finalize(payload, request))
    except ValidationError as exc:
        logger.warning("repair round also failed validation: %s", exc)
        return None
