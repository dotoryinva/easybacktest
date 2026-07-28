"""Allocation utilities beyond backtesting (Change 15) — portfolio extraction."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..backtest.allocation_algorithms import AlgorithmUnavailable
from ..backtest.allocation_engine import extract_portfolio
from ..backtest.quant_engine import QuantBacktestError
from ..schemas import ExtractPortfolioRequest, ExtractPortfolioResponse
from ..services import data_service

router = APIRouter(prefix="/api/allocation", tags=["allocation"])


@router.post("/extract-portfolio", response_model=ExtractPortfolioResponse)
def extract(body: ExtractPortfolioRequest) -> ExtractPortfolioResponse:
    """Today's actionable target book: integer share counts + KRW remainder for `capital`."""
    try:
        return extract_portfolio(body.strategy, body.as_of_date, body.capital)
    except (AlgorithmUnavailable, QuantBacktestError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except data_service.InvalidTicker as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
