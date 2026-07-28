"""Retirement Monte Carlo (Change 17).

Vectorised numpy simulation of a savings balance from `current_age` to `end_age`. During the
working years contributions are added; from `retirement_age` on, inflation-adjusted spending
is withdrawn. Annual returns are i.i.d. Normal(expected_return, volatility). Cash flows given
in today's money are grown by inflation. Reports percentile balance bands, the probability of
staying solvent, and the inflation-adjusted spending level that reaches ~90% success.
"""
from __future__ import annotations

import numpy as np

from ..schemas import (
    RetirementBand,
    RetirementRequest,
    RetirementResponse,
)

_TARGET_SUCCESS = 0.90


def _simulate(req: RetirementRequest, returns: np.ndarray, annual_spending: float):
    """Return (ages, balances[n_sims, n_ages]) for a given spending level."""
    ages = list(range(req.current_age, req.end_age + 1))
    n_sims = returns.shape[0]
    bal = np.full(n_sims, float(req.current_savings))
    balances = np.empty((n_sims, len(ages)))
    balances[:, 0] = bal

    for i in range(len(ages) - 1):
        age = ages[i]
        infl = (1.0 + req.inflation) ** i
        bal = bal * (1.0 + returns[:, i])
        if age < req.retirement_age:
            bal = bal + req.annual_contribution * infl
        else:
            bal = bal - annual_spending * infl
        bal = np.maximum(bal, 0.0)
        balances[:, i + 1] = bal
    return ages, balances


def _success(balances: np.ndarray) -> float:
    return float(np.mean(balances[:, -1] > 0.0))


def _safe_spending(req: RetirementRequest, returns: np.ndarray) -> float:
    """Largest inflation-adjusted spending whose success ≥ 90% (bisection on fixed draws)."""
    def success_at(spend: float) -> float:
        return _success(_simulate(req, returns, spend)[1])

    lo, hi = 0.0, max(req.annual_spending * 2.0, req.current_savings * 0.15, 1.0)
    # Grow the ceiling until it clearly fails, so the target is bracketed.
    for _ in range(8):
        if success_at(hi) < _TARGET_SUCCESS:
            break
        hi *= 1.6
    for _ in range(28):
        mid = (lo + hi) / 2.0
        if success_at(mid) >= _TARGET_SUCCESS:
            lo = mid
        else:
            hi = mid
    return round(lo, 2)


def simulate(req: RetirementRequest) -> RetirementResponse:
    ages = list(range(req.current_age, req.end_age + 1))
    n_years = len(ages) - 1
    rng = np.random.default_rng(12345)  # fixed so bands and safe-spending are consistent
    returns = rng.normal(req.expected_return, req.volatility, size=(req.num_simulations, n_years))

    _, balances = _simulate(req, returns, req.annual_spending)

    pcts = np.percentile(balances, [10, 25, 50, 75, 90], axis=0)
    bands = [
        RetirementBand(
            age=ages[i],
            p10=round(float(pcts[0, i]), 2),
            p25=round(float(pcts[1, i]), 2),
            p50=round(float(pcts[2, i]), 2),
            p75=round(float(pcts[3, i]), 2),
            p90=round(float(pcts[4, i]), 2),
        )
        for i in range(len(ages))
    ]

    ending = balances[:, -1]
    # Age at which each path first hits zero (∞ for paths that never deplete).
    depleted = np.where(balances <= 0.0, np.array(ages)[None, :], np.inf).min(axis=1)
    median_depletion = np.median(depleted)
    depletion_age = None if not np.isfinite(median_depletion) else int(median_depletion)

    return RetirementResponse(
        bands=bands,
        success_probability=round(_success(balances), 4),
        median_ending_balance=round(float(np.median(ending)), 2),
        depletion_age_p50=depletion_age,
        safe_annual_spending=_safe_spending(req, returns),
    )
