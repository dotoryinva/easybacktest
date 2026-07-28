from fastapi import APIRouter, HTTPException, Query

from ..schemas import (
    SavedStrategy,
    SaveStrategyRequest,
    Strategy,
    UpdateStrategyRequest,
)
from ..services import strategy_service

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.post("", response_model=Strategy, status_code=201)
def create(body: SaveStrategyRequest) -> Strategy:
    return strategy_service.save(body.strategy, body.user_id)


@router.get("", response_model=list[SavedStrategy])
def list_strategies(
    user_id: str = Query(min_length=1, max_length=64),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[SavedStrategy]:
    return strategy_service.list_for_user(user_id, limit)


@router.get("/{strategy_id}", response_model=SavedStrategy)
def get_one(strategy_id: str) -> SavedStrategy:
    try:
        return strategy_service.get(strategy_id)
    except strategy_service.StrategyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{strategy_id}/runs")
def recent_runs(strategy_id: str, limit: int = Query(default=5, ge=1, le=20)) -> list[dict]:
    try:
        strategy_service.get(strategy_id)
    except strategy_service.StrategyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return strategy_service.recent_runs(strategy_id, limit)


@router.patch("/{strategy_id}", response_model=Strategy)
def update(strategy_id: str, body: UpdateStrategyRequest) -> Strategy:
    try:
        return strategy_service.update(strategy_id, body.strategy, body.user_id)
    except strategy_service.StrategyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{strategy_id}/duplicate", response_model=Strategy, status_code=201)
def duplicate(strategy_id: str, user_id: str = Query(min_length=1, max_length=64)) -> Strategy:
    try:
        return strategy_service.duplicate(strategy_id, user_id)
    except strategy_service.StrategyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{strategy_id}", status_code=204)
def delete(strategy_id: str, user_id: str = Query(min_length=1, max_length=64)) -> None:
    try:
        strategy_service.delete(strategy_id, user_id)
    except strategy_service.StrategyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
