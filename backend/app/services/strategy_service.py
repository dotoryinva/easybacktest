"""CRUD for saved strategies and their backtest run history."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from ulid import ULID

from ..db import connect
from ..schemas import BacktestParams, BacktestResult, SavedStrategy, Strategy

logger = logging.getLogger(__name__)


class StrategyNotFound(LookupError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_saved(row) -> SavedStrategy:
    return SavedStrategy(
        strategy=Strategy.model_validate_json(row["definition"]),
        user_id=row["user_id"],
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def save(strategy: Strategy, user_id: str) -> Strategy:
    """Insert, or update in place when the id already belongs to this user."""
    now = _now()
    payload = strategy.model_dump_json()
    with connect() as conn:
        existing = conn.execute(
            "SELECT user_id FROM strategies WHERE id = ?", (strategy.id,)
        ).fetchone()
        if existing and existing["user_id"] != user_id:
            # Saving someone else's strategy forks it rather than overwriting.
            strategy = strategy.model_copy(update={"id": str(ULID())})
            payload = strategy.model_dump_json()
            existing = None

        if existing:
            conn.execute(
                """UPDATE strategies
                   SET name = ?, description = ?, language = ?, definition = ?, updated_at = ?
                   WHERE id = ?""",
                (strategy.name, strategy.description, strategy.language, payload, now, strategy.id),
            )
        else:
            conn.execute(
                """INSERT INTO strategies
                   (id, user_id, name, description, language, definition, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    strategy.id, user_id, strategy.name, strategy.description,
                    strategy.language, payload, strategy.created_at.isoformat(), now,
                ),
            )
    return strategy


def list_for_user(user_id: str, limit: int = 200) -> list[SavedStrategy]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT * FROM strategies
               WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    return [_row_to_saved(r) for r in rows]


def get(strategy_id: str) -> SavedStrategy:
    with connect() as conn:
        row = conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
    if row is None:
        raise StrategyNotFound(f"strategy {strategy_id} not found")
    return _row_to_saved(row)


def update(strategy_id: str, strategy: Strategy, user_id: str) -> Strategy:
    saved = get(strategy_id)
    if saved.user_id != user_id:
        raise StrategyNotFound(f"strategy {strategy_id} not found")

    merged = strategy.model_copy(update={"id": strategy_id, "created_at": saved.strategy.created_at})
    with connect() as conn:
        conn.execute(
            """UPDATE strategies
               SET name = ?, description = ?, language = ?, definition = ?, updated_at = ?
               WHERE id = ? AND user_id = ?""",
            (
                merged.name, merged.description, merged.language,
                merged.model_dump_json(), _now(), strategy_id, user_id,
            ),
        )
    return merged


def delete(strategy_id: str, user_id: str) -> None:
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM strategies WHERE id = ? AND user_id = ?", (strategy_id, user_id)
        )
        if cur.rowcount == 0:
            raise StrategyNotFound(f"strategy {strategy_id} not found")


def duplicate(strategy_id: str, user_id: str) -> Strategy:
    saved = get(strategy_id)
    clone = saved.strategy.model_copy(
        update={
            "id": str(ULID()),
            "name": f"{saved.strategy.name} (copy)",
            "created_at": datetime.now(timezone.utc),
        }
    )
    return save(clone, user_id)


# --------------------------------------------------------------------------- #
# Run history
# --------------------------------------------------------------------------- #


def record_run(result: BacktestResult, user_id: str) -> None:
    """Persist metrics only — equity curves and trade logs are cheap to recompute."""
    if not result.strategy_id:
        return
    with connect() as conn:
        known = conn.execute(
            "SELECT 1 FROM strategies WHERE id = ?", (result.strategy_id,)
        ).fetchone()
        if not known:
            return
        conn.execute(
            """INSERT INTO backtest_runs
               (id, strategy_id, user_id, ticker, market, params, metrics, ran_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(ULID()), result.strategy_id, user_id,
                result.params.ticker, result.params.market,
                result.params.model_dump_json(), result.metrics.model_dump_json(),
                result.ran_at.isoformat(),
            ),
        )


def recent_runs(strategy_id: str, limit: int = 5) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT ticker, market, params, metrics, ran_at
               FROM backtest_runs WHERE strategy_id = ?
               ORDER BY ran_at DESC LIMIT ?""",
            (strategy_id, limit),
        ).fetchall()
    return [
        {
            "ticker": r["ticker"],
            "market": r["market"],
            "params": BacktestParams.model_validate_json(r["params"]).model_dump(mode="json"),
            "metrics": json.loads(r["metrics"]),
            "ran_at": r["ran_at"],
        }
        for r in rows
    ]
