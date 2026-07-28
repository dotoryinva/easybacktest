import logging

from fastapi import APIRouter, Header, HTTPException

from ..backtest.allocation_algorithms import AlgorithmUnavailable
from ..backtest.allocation_engine import (
    extract_portfolio,
    run_allocation_backtest,
    run_static_allocation,
)
from ..backtest.engine import BacktestError, run_backtest
from ..backtest.quant_engine import QuantBacktestError, run_quant_backtest
from ..backtest.rotation_engine import run_dynamic_allocation
from ..schemas import (
    BacktestResult,
    DynamicAllocationRequest,
    ExtractPortfolioRequest,
    ExtractPortfolioResponse,
    RunAllocationRequest,
    RunBacktestRequest,
    RunQuantBacktestRequest,
    StaticAllocationRequest,
)
from ..services import data_service, strategy_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router.post("/run", response_model=BacktestResult)
def run(
    body: RunBacktestRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> BacktestResult:
    try:
        result = run_backtest(body.strategy, body.params)
    except data_service.InvalidTicker as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except data_service.TickerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BacktestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if x_user_id:
        try:
            strategy_service.record_run(result, x_user_id)
        except Exception:  # noqa: BLE001 - history is best-effort
            logger.exception("failed to record run history")

    return result


@router.post("/quant", response_model=BacktestResult)
def run_quant(body: RunQuantBacktestRequest) -> BacktestResult:
    """Factor-ranked multi-stock portfolio backtest (Change 13, Family B)."""
    try:
        return run_quant_backtest(body.strategy, body.params)
    except QuantBacktestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except data_service.InvalidTicker as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/allocation/static", response_model=BacktestResult)
def run_allocation(body: StaticAllocationRequest) -> BacktestResult:
    """Fixed-weight asset-allocation backtest (Change 14, 정적배분)."""
    try:
        return run_static_allocation(body)
    except QuantBacktestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except data_service.InvalidTicker as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/allocation/dynamic", response_model=BacktestResult)
def run_dynamic(body: DynamicAllocationRequest) -> BacktestResult:
    """Rule-based rotation backtest — GEM / VAA / LAA / GTAA (Change 14, 동적배분)."""
    try:
        return run_dynamic_allocation(body)
    except QuantBacktestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except data_service.InvalidTicker as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/allocation", response_model=BacktestResult)
def run_allocation_unified(body: RunAllocationRequest) -> BacktestResult:
    """Unified asset-allocation backtest — algorithm + band + market timing (Change 15)."""
    try:
        return run_allocation_backtest(body.strategy, body.params)
    except AlgorithmUnavailable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except QuantBacktestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except data_service.InvalidTicker as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
