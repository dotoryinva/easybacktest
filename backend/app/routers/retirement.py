"""Retirement Monte Carlo endpoint (Change 17)."""
from __future__ import annotations

from fastapi import APIRouter

from ..schemas import RetirementRequest, RetirementResponse
from ..services import retirement

router = APIRouter(prefix="/api/retirement", tags=["retirement"])


@router.post("/simulate", response_model=RetirementResponse)
def simulate(body: RetirementRequest) -> RetirementResponse:
    return retirement.simulate(body)
