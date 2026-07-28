import logging

from fastapi import APIRouter, HTTPException

from ..schemas import ClarificationResponse, ParsedStrategyResponse, ParseStrategyRequest
from ..services import ai_parser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/parse-strategy", response_model=ParsedStrategyResponse | ClarificationResponse)
def parse_strategy(body: ParseStrategyRequest):
    try:
        return ai_parser.parse_strategy(body)
    except ai_parser.AIParserUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ai_parser.AIParserError as exc:
        logger.warning("strategy parse failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
