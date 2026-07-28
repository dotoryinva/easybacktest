"""QuantStats HTML tearsheet download (Change 16).

The frontend POSTs a backtest's daily equity + benchmark series; we return the same rich,
self-contained HTML report Quantus produces, as a file download.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..schemas import QuantStatsReportRequest
from ..services.report_service import ReportError, generate_quantstats_html, html_to_pdf

router = APIRouter(prefix="/api/report", tags=["report"])


def _safe_filename(title: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', " ", title).strip()
    return (cleaned or "backtest_report")[:120]


@router.post("/quantstats")
def quantstats(body: QuantStatsReportRequest) -> Response:
    try:
        html = generate_quantstats_html(
            [p.date for p in body.points],
            [p.strategy for p in body.points],
            [p.benchmark for p in body.points],
            body.title,
        )
        if body.format == "pdf":
            content: bytes | str = html_to_pdf(html)
            media_type, ext = "application/pdf", "pdf"
        else:
            content, media_type, ext = html, "text/html; charset=utf-8", "html"
    except ReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    name = _safe_filename(body.title)
    # RFC 5987 encoding so Korean/other non-ASCII titles survive the header.
    disposition = (
        f'attachment; filename="report.{ext}"; '
        f"filename*=UTF-8''{quote(name)}.{ext}"
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )
