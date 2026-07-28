"""QuantStats HTML tearsheet generation (Change 16).

Turns a backtest's daily equity + benchmark series into the same rich, self-contained HTML
report Quantus produces — ~60 metrics, cumulative/log/rolling charts, a monthly-returns
heatmap, EOY table and worst-drawdown table — via the `quantstats` library. Matplotlib runs
headless (Agg). Heavy imports are deferred to the first call so app startup stays fast.
"""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import date

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ReportError(RuntimeError):
    """The report could not be generated from the supplied series."""


def _returns(values: list[float], index: pd.DatetimeIndex) -> pd.Series:
    s = pd.Series(values, index=index, dtype="float64").replace(0.0, np.nan)
    return s.pct_change().replace([np.inf, -np.inf], np.nan)


def generate_quantstats_html(
    dates: list[date],
    strategy_values: list[float],
    benchmark_values: list[float],
    title: str,
) -> str:
    if len(dates) < 20:
        raise ReportError("not enough history for a report (need ≥ 20 daily points)")

    import matplotlib  # noqa: PLC0415 - heavy, defer to first call

    matplotlib.use("Agg")
    import quantstats as qs  # noqa: PLC0415

    idx = pd.DatetimeIndex(pd.to_datetime(pd.Series(dates)))
    strat = _returns(strategy_values, idx).dropna()
    if len(strat) < 10:
        raise ReportError("strategy series has too few valid daily returns")

    bench = _returns(benchmark_values, idx).reindex(strat.index)
    # Only include the benchmark if it actually varies — a flat line breaks beta/alpha.
    use_benchmark = bench.notna().sum() > 5 and float(bench.std(ddof=0) or 0.0) > 1e-9
    benchmark = bench.fillna(0.0) if use_benchmark else None

    fd, path = tempfile.mkstemp(suffix=".html")
    os.close(fd)
    try:
        qs.reports.html(strat, benchmark=benchmark, output=path, title=title)
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except Exception as exc:  # noqa: BLE001 - surface a clean 422 to the client
        logger.exception("quantstats report failed")
        raise ReportError(f"report generation failed: {exc}") from exc
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def html_to_pdf(html: str) -> bytes:
    """Render a report HTML string to PDF bytes with headless Chromium (Playwright).

    Chromium is used because the tearsheet is SVG-and-CSS heavy — a browser engine is the
    only thing that reproduces it faithfully. Runs synchronously; FastAPI dispatches the
    endpoint on a worker thread with no event loop, which is what the sync API needs.
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415 - heavy, lazy
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ReportError("PDF export is unavailable (playwright not installed)") from exc

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="networkidle")
                pdf = page.pdf(
                    format="A4",
                    print_background=True,
                    margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"},
                )
            finally:
                browser.close()
        return pdf
    except ReportError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("html→pdf conversion failed")
        raise ReportError(
            "PDF 변환에 실패했습니다. Chromium이 설치되어 있는지 확인하세요 "
            "(`python -m playwright install chromium`)."
        ) from exc
