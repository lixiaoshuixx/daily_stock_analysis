# -*- coding: utf-8 -*-
"""
===================================
Restructuring analysis API schemas
===================================

Request/response models for restructuring path and timeline APIs.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --- Request ---

class RestructuringAnalyzeRequest(BaseModel):
    """Request to run restructuring analysis for a stock."""

    code: str = Field(..., description="Stock code (e.g. 600519)", min_length=1, max_length=20)
    name: Optional[str] = Field(None, description="Stock name (optional, resolved if not given)")
    use_llm: bool = Field(True, description="Whether to use LLM for path/timeline generation")
    keep_latest_only: bool = Field(
        False, description="If True, after saving the new analysis, delete older analyses for this stock so only the latest remains"
    )


class RestructuringPrepareRequest(BaseModel):
    """Request to run data preparation only (no path analysis LLM)."""

    code: str = Field(..., description="Stock code (e.g. 600519)", min_length=1, max_length=20)
    name: Optional[str] = Field(None, description="Stock name (optional)")


class RestructuringPrepareResponse(BaseModel):
    """Response after data preparation only."""

    success: bool = True
    message: Optional[str] = Field(None, description="Success message (e.g. 上下文已更新)")
    error: Optional[str] = Field(None, description="Error message when success is False")
    prepared_at: Optional[str] = Field(None, description="ISO8601 timestamp when context file was written")


class RestructuringPrepareInfoResponse(BaseModel):
    """Latest data preparation time for a stock (from reports/{code}_restructuring_context.txt mtime)."""

    prepared_at: Optional[str] = Field(None, description="ISO8601 timestamp of last prepare, or null if never prepared")


class RestructuringGroundTruthCreate(BaseModel):
    """Request to add a user-provided ground-truth message or time point."""

    code: str = Field(..., description="Stock code", min_length=1, max_length=20)
    content: str = Field(..., description="Message or event description", min_length=1)
    event_date: Optional[date] = Field(None, description="Event date (YYYY-MM-DD)")
    source: Optional[str] = Field(None, description="Source of the info (e.g. announcement, news)")


# --- Response (nested) ---

class TimelineNodeOut(BaseModel):
    """Single timeline node."""

    id: Optional[int] = None
    event_type: Optional[str] = None
    event_date: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    verified_by_user: bool = False


class RestructuringAnalysisOut(BaseModel):
    """One restructuring analysis with timeline."""

    id: int
    code: str
    name: Optional[str] = None
    summary: Optional[str] = None
    path_description: Optional[str] = None
    raw_context: Optional[str] = None
    created_at: Optional[str] = None
    timeline: List[TimelineNodeOut] = []


class RestructuringAnalyzeResponse(BaseModel):
    """Response after running restructuring analysis."""

    success: bool = True
    analysis_id: int = Field(..., description="Saved analysis id")
    result: Optional[RestructuringAnalysisOut] = Field(None, description="Full analysis with timeline")


class RestructuringAnalysisListItem(BaseModel):
    """List item for analysis history."""

    id: int
    code: str
    name: Optional[str] = None
    summary: Optional[str] = None
    path_description: Optional[str] = None
    created_at: Optional[str] = None


class RestructuringGroundTruthOut(BaseModel):
    """One ground-truth entry."""

    id: int
    code: str
    content: str
    event_date: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[str] = None
