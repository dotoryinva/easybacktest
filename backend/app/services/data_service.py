"""Access to the local Parquet OHLCV cache, via DuckDB.

Reads come straight from the cache. On a cache miss for a ticker that IS in the
universe metadata, `ensure_cached` downloads its history on demand (lazy loading) and
writes the Parquet file — so the cache fills as users explore, rather than requiring a
full up-front bootstrap. A request for a ticker not in the universe raises
`TickerNotFound`, which the routers turn into a 404.
"""
from __future__ import annotations

import logging
import re
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd

from ..config import settings
from ..schemas import Ticker

# 15 years is enough history for every backtest window the UI offers.
LAZY_HISTORY_YEARS = 15
_ensure_locks: dict[tuple[str, str], threading.Lock] = {}
_ensure_locks_guard = threading.Lock()

logger = logging.getLogger(__name__)

# Guards against path traversal: ticker names come straight off the URL.
# A single leading `^` is allowed for index symbols (^GSPC, ^IXIC, ...); everything
# after it is restricted to the same safe alphabet as a normal ticker, so no `.`, `/`
# or `\` sequence can walk out of the market directory.
_TICKER_RE = re.compile(r"^\^?[A-Za-z0-9][A-Za-z0-9._-]{0,14}$")
_MARKETS = ("KR", "US")

_conn = duckdb.connect(database=":memory:")
_conn_lock = threading.Lock()

_ticker_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_ticker_cache_lock = threading.Lock()


class TickerNotFound(LookupError):
    """The requested ticker is not in the local cache."""


class InvalidTicker(ValueError):
    """The requested ticker or market is malformed."""


def validate(ticker: str, market: str) -> tuple[str, str]:
    if market not in _MARKETS:
        raise InvalidTicker(f"market must be one of {_MARKETS}, got {market!r}")
    if not _TICKER_RE.match(ticker or ""):
        raise InvalidTicker(f"invalid ticker {ticker!r}")
    if ".." in ticker:
        raise InvalidTicker(f"invalid ticker {ticker!r}")
    return (ticker.upper() if market == "US" else ticker), market


def _encode_filename(ticker: str) -> str:
    """Map a ticker symbol to its on-disk stem.

    Index symbols carry a leading `^` (`^GSPC`), which is awkward in a path and is a
    glob/shell metacharacter. Replace it with `_` on disk; the original symbol stays
    canonical in the metadata table and across the whole API surface.
    """
    return f"_{ticker[1:]}" if ticker.startswith("^") else ticker


def _decode_filename(stem: str) -> str:
    """Inverse of `_encode_filename` — used when listing what's cached on disk."""
    return f"^{stem[1:]}" if stem.startswith("_") else stem


def ohlcv_file(ticker: str, market: str) -> Path:
    ticker, market = validate(ticker, market)
    return settings.ohlcv_path / market / f"{_encode_filename(ticker)}.parquet"


def tickers_file(market: str) -> Path:
    if market not in _MARKETS:
        raise InvalidTicker(f"unknown market {market!r}")
    return settings.tickers_path / f"{market}.parquet"


def _query(sql: str, params: list) -> pd.DataFrame:
    with _conn_lock:
        return _conn.execute(sql, params).df()


# --------------------------------------------------------------------------- #
# OHLCV
# --------------------------------------------------------------------------- #


def get_ohlcv(
    ticker: str,
    market: str,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    """Cached daily bars in [start, end], inclusive.

    Returns columns [date, open, high, low, close, volume, adj_close] with `date` as a
    python `date`-typed column, sorted ascending.
    """
    path = ohlcv_file(ticker, market)
    if not path.exists():
        raise TickerNotFound(
            f"{market}/{ticker} is not in the local cache. "
            "Run scripts/bootstrap_data.py to add it."
        )

    clauses, params = [], [str(path)]
    if start is not None:
        clauses.append("date >= ?")
        params.append(start)
    if end is not None:
        clauses.append("date <= ?")
        params.append(end)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    df = _query(
        f"""
        SELECT date, open, high, low, close, volume, adj_close
        FROM read_parquet(?)
        {where}
        ORDER BY date
        """,
        params,
    )
    if df.empty:
        raise TickerNotFound(
            f"no cached rows for {market}/{ticker} between {start} and {end}"
        )
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df.reset_index(drop=True)


def cached_range(ticker: str, market: str) -> tuple[date, date] | None:
    path = ohlcv_file(ticker, market)
    if not path.exists():
        return None
    df = _query("SELECT min(date) AS lo, max(date) AS hi FROM read_parquet(?)", [str(path)])
    if df.empty or pd.isna(df.at[0, "lo"]):
        return None
    return (pd.Timestamp(df.at[0, "lo"]).date(), pd.Timestamp(df.at[0, "hi"]).date())


def list_cached(market: str) -> list[str]:
    """Canonical ticker symbols with a local Parquet file (`_GSPC.parquet` → `^GSPC`)."""
    directory = settings.ohlcv_path / market
    if not directory.exists():
        return []
    return sorted(_decode_filename(p.stem) for p in directory.glob("*.parquet"))


def write_ohlcv(df: pd.DataFrame, ticker: str, market: str) -> Path:
    """Overwrite a ticker's Parquet file (ingestion only)."""
    path = ohlcv_file(ticker, market)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out = out.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    out.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
    return path


def upsert_ohlcv(df: pd.DataFrame, ticker: str, market: str) -> int:
    """Merge new rows into an existing file; returns the resulting row count."""
    path = ohlcv_file(ticker, market)
    if path.exists():
        existing = pd.read_parquet(path)
        df = pd.concat([existing, df], ignore_index=True)
    write_ohlcv(df, ticker, market)
    return len(pd.read_parquet(path))


# --------------------------------------------------------------------------- #
# Lazy loading + popularity
# --------------------------------------------------------------------------- #


def in_universe(ticker: str, market: str) -> bool:
    """True when the ticker exists in the market's metadata table."""
    ticker, market = validate(ticker, market)
    df = _load_tickers(market)
    if df.empty:
        return False
    return bool((df["ticker"].astype(str).str.upper() == ticker.upper()).any())


def _ensure_lock(ticker: str, market: str) -> threading.Lock:
    """A per-ticker lock so two concurrent first-requests don't double-download."""
    key = (market, ticker.upper())
    with _ensure_locks_guard:
        lock = _ensure_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _ensure_locks[key] = lock
        return lock


def ensure_cached(
    ticker: str,
    market: str,
    years: int = LAZY_HISTORY_YEARS,
    start: date | None = None,
) -> bool:
    """Guarantee the local OHLCV file exists *and* reaches back far enough.

    Downloads on first request. When `start` is given and the cached window begins
    after it (e.g. a ticker bootstrapped with only 5 years, now needed from 2019), the
    history is re-fetched wider and overwritten — otherwise the caller would silently
    get a truncated series. Returns True if a download happened.

    Raises `TickerNotFound` when the ticker is unknown to the universe (so we never
    hammer a provider with arbitrary URL input) or when every provider fails.
    """
    ticker, market = validate(ticker, market)
    path = ohlcv_file(ticker, market)

    if path.exists():
        if start is None:
            return False
        covered = cached_range(ticker, market)
        if covered is not None and covered[0] <= start:
            return False  # already deep enough
    elif not in_universe(ticker, market):
        raise TickerNotFound(f"{market}/{ticker} is not in the ticker universe")

    with _ensure_lock(ticker, market):
        covered = cached_range(ticker, market) if path.exists() else None
        if covered is not None and (start is None or covered[0] <= start):
            return False  # another thread won the race while we waited
        # Providers are only imported here so request-time reads stay import-light.
        from ..data_providers import DataProviderError, fetch_ohlcv  # noqa: PLC0415

        end = date.today()
        default_start = end - timedelta(days=int(years * 365.25) + 5)
        # Always fetch at least the default depth, and deeper if the caller needs it.
        fetch_start = min(start, default_start) if start is not None else default_start
        try:
            df = fetch_ohlcv(ticker, market, fetch_start, end)
        except DataProviderError as exc:
            if covered is not None:
                # Keep the (shorter) history we already have rather than losing it.
                logger.warning("could not widen %s/%s: %s", market, ticker, exc)
                return False
            raise TickerNotFound(
                f"could not fetch {market}/{ticker} from any provider: {exc}"
            ) from exc
        write_ohlcv(df, ticker, market)
        logger.info(
            "lazy-cached %s/%s (%d rows from %s)", market, ticker, len(df), fetch_start
        )
        return True


def record_query(ticker: str, market: str) -> None:
    """Bump the popularity counter for a ticker. Best-effort; never raises."""
    try:
        ticker, market = validate(ticker, market)
    except InvalidTicker:
        return
    now = datetime.now(timezone.utc).isoformat()
    try:
        from ..db import connect  # noqa: PLC0415 - avoid a circular import at module load

        with connect() as conn:
            conn.execute(
                """
                INSERT INTO ticker_popularity (market, ticker, query_count, last_queried_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(market, ticker) DO UPDATE SET
                    query_count = query_count + 1,
                    last_queried_at = excluded.last_queried_at
                """,
                [market, ticker.upper(), now],
            )
    except Exception:  # noqa: BLE001 - popularity is telemetry, not a hard dependency
        logger.debug("record_query failed for %s/%s", market, ticker, exc_info=True)


def popularity_map(market: str) -> dict[str, int]:
    """`{TICKER: query_count}` for a market, used as a search tie-breaker."""
    try:
        from ..db import connect  # noqa: PLC0415

        with connect() as conn:
            rows = conn.execute(
                "SELECT ticker, query_count FROM ticker_popularity WHERE market = ?",
                [market],
            ).fetchall()
        return {str(r["ticker"]).upper(): int(r["query_count"]) for r in rows}
    except Exception:  # noqa: BLE001
        return {}


def recently_queried(days: int = 30) -> list[tuple[str, str]]:
    """`[(ticker, market), ...]` queried within `days` — the nightly refresh warm set."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        from ..db import connect  # noqa: PLC0415

        with connect() as conn:
            rows = conn.execute(
                "SELECT market, ticker FROM ticker_popularity WHERE last_queried_at >= ?",
                [cutoff],
            ).fetchall()
        return [(str(r["ticker"]), str(r["market"])) for r in rows]
    except Exception:  # noqa: BLE001
        return []


# --------------------------------------------------------------------------- #
# Ticker metadata
# --------------------------------------------------------------------------- #


def _load_tickers(market: str) -> pd.DataFrame:
    """Ticker metadata for a market, memoised on the file's mtime."""
    path = tickers_file(market)
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "ticker", "name_en", "name_ko", "market", "sector", "industry",
                "board", "kind", "is_tradable", "aliases",
            ]
        )
    mtime = path.stat().st_mtime
    with _ticker_cache_lock:
        hit = _ticker_cache.get(market)
        if hit and hit[0] == mtime:
            return hit[1]
    df = pd.read_parquet(path)
    for col in ("name_en", "name_ko", "sector", "industry", "board"):
        if col not in df.columns:
            df[col] = None
    # Tables written before the kind/is_tradable/aliases columns existed still load.
    if "kind" not in df.columns:
        df["kind"] = "stock"
    if "is_tradable" not in df.columns:
        df["is_tradable"] = True
    if "aliases" not in df.columns:
        df["aliases"] = ""
    df["kind"] = df["kind"].fillna("stock")
    df["is_tradable"] = df["is_tradable"].fillna(True).astype(bool)
    df["aliases"] = df["aliases"].fillna("")
    df["ticker"] = df["ticker"].astype(str)
    with _ticker_cache_lock:
        _ticker_cache[market] = (mtime, df)
    return df


def write_tickers(df: pd.DataFrame, market: str) -> Path:
    path = tickers_file(market)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
    with _ticker_cache_lock:
        _ticker_cache.pop(market, None)
    return path


def _row_to_ticker(row: pd.Series) -> Ticker:
    def clean(v) -> str | None:
        return None if v is None or pd.isna(v) else str(v)

    return Ticker(
        ticker=str(row["ticker"]),
        name_en=clean(row.get("name_en")) or str(row["ticker"]),
        name_ko=clean(row.get("name_ko")),
        market=row["market"],
        sector=clean(row.get("sector")),
        industry=clean(row.get("industry")),
        kind=clean(row.get("kind")) or "stock",
        is_tradable=bool(row.get("is_tradable", True)),
        aliases=clean(row.get("aliases")) or "",
    )


def get_ticker(ticker: str, market: str) -> Ticker:
    ticker, market = validate(ticker, market)
    df = _load_tickers(market)
    hit = df[df["ticker"].str.upper() == ticker.upper()]
    if hit.empty:
        raise TickerNotFound(f"{market}/{ticker} is not in the ticker universe")
    return _row_to_ticker(hit.iloc[0])


# Korean ETF product names are written in Latin ("TIGER 미국S&P500"), so a search in
# Korean phonetics must be expanded to the Latin brand to match them.
_BRAND_SYNONYMS = {
    "타이거": "tiger",
    "코덱스": "kodex",
    "아리랑": "arirang",
    "케이비스타": "kbstar",
    "하나로": "hanaro",
    "코세프": "kosef",
    "플러스": "plus",
    "라이즈": "rise",
}


def _expand_terms(q_lower: str) -> list[str]:
    """The query plus any brand transliteration it implies (deduped, query first)."""
    terms = [q_lower]
    for phonetic, latin in _BRAND_SYNONYMS.items():
        if phonetic in q_lower and latin not in terms:
            terms.append(latin)
    return terms


def _match_score(term: str, tl: str, enl: str, kol: str, alias_terms: set[str]) -> int | None:
    """Rank a single row against a single term; None when it doesn't match at all."""
    if tl == term:
        return 0
    if tl.startswith(term):
        return 1
    if term in alias_terms:
        return 2
    if enl.startswith(term) or kol.startswith(term):
        return 3
    if term in enl or term in kol:
        return 4
    if any(term in a for a in alias_terms):
        return 5
    return None


def search_tickers(
    query: str, market: str | None = None, limit: int = 20, cached_only: bool = False
) -> list[Ticker]:
    """Ranked search over ticker code, English/Korean name and aliases.

    Ranking (lower is better): exact code < code prefix < exact alias < name prefix <
    name substring < alias substring. Ties break on tradable-first, then popularity
    (query_count desc), then shorter code, then alphabetical. `cached_only=True` keeps
    only tickers with a local Parquet file — otherwise the whole universe is searchable
    and OHLCV is fetched lazily on first open.
    """
    markets = [market] if market else list(_MARKETS)
    q = (query or "").strip()
    if not q:
        return []
    terms = _expand_terms(q.lower())

    scored: list[tuple[tuple, Ticker]] = []
    for mk in markets:
        df = _load_tickers(mk)
        if df.empty:
            continue
        available = set(list_cached(mk)) if cached_only else None
        pop = popularity_map(mk)

        code_l = df["ticker"].astype(str).str.lower()
        en_l = df["name_en"].fillna("").astype(str).str.lower()
        ko_l = df["name_ko"].fillna("").astype(str).str.lower()
        al_l = df["aliases"].fillna("").astype(str).str.lower()

        mask = pd.Series(False, index=df.index)
        for term in terms:
            mask |= (
                code_l.str.contains(term, regex=False)
                | en_l.str.contains(term, regex=False)
                | ko_l.str.contains(term, regex=False)
                | al_l.str.contains(term, regex=False)
            )

        for _, row in df[mask].iterrows():
            t = str(row["ticker"])
            if available is not None and t not in available:
                continue
            tl = t.lower()
            enl = str(row["name_en"] or "").lower()
            kol = str(row["name_ko"] or "").lower()
            alias_terms = {a.strip().lower() for a in str(row["aliases"] or "").split(";") if a.strip()}

            scores = [
                s for term in terms
                if (s := _match_score(term, tl, enl, kol, alias_terms)) is not None
            ]
            if not scores:
                continue
            score = min(scores)

            tradable_rank = 0 if bool(row.get("is_tradable", True)) else 1
            popularity = pop.get(t.upper(), 0)
            key = (score, tradable_rank, -popularity, len(t), t)
            scored.append((key, _row_to_ticker(row)))

    scored.sort(key=lambda x: x[0])
    return [t for _, t in scored[:limit]]


def board_of(ticker: str, market: str) -> str | None:
    """KOSPI / KOSDAQ / US / ETF — drives the KR sell-tax rate."""
    ticker, market = validate(ticker, market)
    df = _load_tickers(market)
    hit = df[df["ticker"].str.upper() == ticker.upper()]
    if hit.empty:
        return None
    value = hit.iloc[0].get("board")
    return None if value is None or pd.isna(value) else str(value)
