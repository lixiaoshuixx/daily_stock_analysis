# -*- coding: utf-8 -*-
"""
===================================
Restructuring analysis API
===================================

- POST /restructuring/analyze: run analysis for a stock code, save result.
- POST /restructuring/prepare: data preparation only (context built and written to reports/), no path LLM.
- GET /restructuring/prepare-info: latest data preparation time for a stock (from context file mtime).
- GET /restructuring/history: list analyses (optional filter by code).
- GET /restructuring/result/{analysis_id}: get one analysis with timeline.
- POST /restructuring/ground-truth: add user-provided message/time point.
- GET /restructuring/ground-truth: list ground-truth entries (optional filter by code).
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.restructuring import (
    RestructuringAnalyzeRequest,
    RestructuringAnalyzeResponse,
    RestructuringAnalysisListItem,
    RestructuringAnalysisOut,
    RestructuringGroundTruthCreate,
    RestructuringGroundTruthOut,
    RestructuringPrepareInfoResponse,
    RestructuringPrepareRequest,
    RestructuringPrepareResponse,
)
from data_provider.base import canonical_stock_code
from src.services.restructuring_service import run_restructuring_analysis, run_restructuring_data_prep_only
from src.storage import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/analyze",
    response_model=RestructuringAnalyzeResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Run restructuring analysis",
    description="Analyze restructuring path and timeline for a stock. Result is saved and reused in next run.",
)
def analyze(request: RestructuringAnalyzeRequest):
    """Run restructuring analysis for the given stock code."""
    code = canonical_stock_code(request.code)
    if not code:
        raise HTTPException(status_code=400, detail="Invalid stock code")
    out = run_restructuring_analysis(
        code=code,
        name=request.name,
        use_llm=request.use_llm,
        keep_latest_only=request.keep_latest_only,
    )
    if not out.get("success"):
        raise HTTPException(status_code=400, detail=out.get("error", "Analysis failed"))
    return RestructuringAnalyzeResponse(
        success=True,
        analysis_id=out["analysis_id"],
        result=RestructuringAnalysisOut(**out["result"]) if out.get("result") else None,
    )


@router.post(
    "/prepare",
    response_model=RestructuringPrepareResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Data preparation only",
    description="Build restructuring context (announcement filter, fetch, strip noise) and write to reports/. No path analysis LLM.",
)
def prepare(request: RestructuringPrepareRequest):
    """Run data preparation only: gather context and write to reports/{code}_restructuring_context.txt."""
    code = canonical_stock_code(request.code)
    if not code:
        raise HTTPException(status_code=400, detail="Invalid stock code")
    out = run_restructuring_data_prep_only(code=code, name=request.name)
    if not out.get("success"):
        raise HTTPException(status_code=400, detail=out.get("error", "Data preparation failed"))
    return RestructuringPrepareResponse(
        success=True,
        message=out.get("message", "上下文已更新"),
        prepared_at=out.get("prepared_at"),
    )


@router.get(
    "/prepare-info",
    response_model=RestructuringPrepareInfoResponse,
    summary="Latest data preparation time",
    description="Return the last-modified time of reports/{code}_restructuring_context.txt for the given stock.",
)
def get_prepare_info(
    code: Optional[str] = Query(None, description="Stock code"),
):
    """Return prepared_at (ISO8601) if context file exists, else null."""
    code = canonical_stock_code(code) if code else None
    if not code:
        return RestructuringPrepareInfoResponse(prepared_at=None)
    path = Path("reports") / f"{code}_restructuring_context.txt"
    if not path.exists():
        return RestructuringPrepareInfoResponse(prepared_at=None)
    try:
        mtime = path.stat().st_mtime
        prepared_at = datetime.fromtimestamp(mtime).isoformat()
        return RestructuringPrepareInfoResponse(prepared_at=prepared_at)
    except OSError:
        return RestructuringPrepareInfoResponse(prepared_at=None)


@router.get(
    "/history",
    response_model=List[RestructuringAnalysisListItem],
    summary="List restructuring analyses",
    description="List saved analyses, optionally filtered by stock code. Newest first.",
)
def list_analyses(
    code: Optional[str] = Query(None, description="Filter by stock code"),
    limit: int = Query(50, ge=1, le=200, description="Max number of records"),
):
    """List restructuring analysis history."""
    db = get_db()
    items = db.get_restructuring_analyses(code=canonical_stock_code(code) if code else None, limit=limit)
    return [RestructuringAnalysisListItem(**x) for x in items]


@router.get(
    "/result/{analysis_id}",
    response_model=RestructuringAnalysisOut,
    responses={404: {"model": ErrorResponse}},
    summary="Get analysis by id",
    description="Get one restructuring analysis with full timeline.",
)
def get_result(analysis_id: int):
    """Get one analysis with timeline."""
    db = get_db()
    result = db.get_restructuring_analysis_with_timeline(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return RestructuringAnalysisOut(**result)


@router.post(
    "/ground-truth",
    response_model=dict,
    responses={400: {"model": ErrorResponse}},
    summary="Add ground-truth message",
    description="Add a user-provided restructuring message or time point for a stock.",
)
def add_ground_truth(body: RestructuringGroundTruthCreate):
    """Add one ground-truth entry."""
    code = canonical_stock_code(body.code)
    if not code:
        raise HTTPException(status_code=400, detail="Invalid stock code")
    db = get_db()
    row_id = db.add_restructuring_ground_truth(
        code=code,
        content=body.content.strip(),
        event_date=body.event_date,
        source=body.source.strip() if body.source else None,
    )
    return {"id": row_id, "code": code}


@router.get(
    "/ground-truth",
    response_model=List[RestructuringGroundTruthOut],
    summary="List ground-truth entries",
    description="List user-provided messages/time points, optionally by stock code.",
)
def list_ground_truth(
    code: Optional[str] = Query(None, description="Filter by stock code"),
    limit: int = Query(200, ge=1, le=500, description="Max number of records"),
):
    """List ground-truth entries."""
    db = get_db()
    items = db.get_restructuring_ground_truth(
        code=canonical_stock_code(code) if code else None, limit=limit
    )
    return [RestructuringGroundTruthOut(**x) for x in items]
