"""Base response models for API endpoints."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from .domain_models import ErrorCode


class Counters(BaseModel):
    """Standard counters for batch operations."""

    success: int = Field(default=0, description="Number of successful operations")
    fail: int = Field(default=0, description="Number of failed operations")
    skip: int = Field(default=0, description="Number of skipped operations")
    update: int = Field(default=0, description="Number of update operations")
    insert: int = Field(default=0, description="Number of insert operations")
    conflict: int = Field(default=0, description="Number of conflict operations")


class Summary(BaseModel):
    """Standard summary for API responses."""

    totalElapsedMs: int = Field(description="Total elapsed time in milliseconds")
    totalSuccess: int = Field(default=0, description="Total successful operations")
    totalFail: int = Field(default=0, description="Total failed operations")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(description="Error message")
    details: Optional[str] = Field(default=None, description="Additional error details")
    code: Optional[ErrorCode] = Field(default=None, description="Error code")


class PhaseCounters(BaseModel):
    """Counters for a specific phase."""

    elapsedMs: int = Field(description="Phase elapsed time in milliseconds")
    counters: Counters = Field(description="Phase operation counters")


class ModeResult(BaseModel):
    """Result for a single mode execution."""

    executed: bool = Field(description="Whether mode was executed")
    elapsedMs: int = Field(description="Elapsed time in milliseconds")
    counters: Counters = Field(description="Operation counters")
    warn: List[str] = Field(default_factory=list, description="Warning codes")


class ConsensusResult(ModeResult):
    """Extended result for consensus mode with Phase 1 and Phase 2."""

    phase1: PhaseCounters = Field(description="Phase 1 (Raw Upsert) results")
    phase2: Dict[str, Any] = Field(description="Phase 2 (Change Detection) results")


class SourceDataResponse(BaseModel):
    """Response for GET /sourceData endpoint."""

    reqId: str = Field(description="Request unique identifier")
    endpoint: str = Field(default="GET /sourceData", description="API endpoint")
    summary: Summary = Field(description="Overall summary")
    results: Dict[str, Any] = Field(description="Results per mode")


class TableProcessingResult(BaseModel):
    """Result for processing a single table."""

    tableName: str = Field(description="Name of the processed table")
    rowsScanned: int = Field(description="Number of rows scanned")
    inserted: int = Field(description="Number of rows inserted")
    conflicts: int = Field(description="Number of conflicts")
    skipped: int = Field(default=0, description="Number of rows skipped")
    skipReason: Optional[str] = Field(default=None, description="Reason for skipping")
    warn: List[str] = Field(default_factory=list, description="Warning codes")


class SetEventsTableResponse(BaseModel):
    """Response for POST /setEventsTable endpoint."""

    reqId: str = Field(description="Request unique identifier")
    endpoint: str = Field(default="POST /setEventsTable", description="API endpoint")
    dryRun: bool = Field(description="Whether this was a dry run")
    summary: Dict[str, Any] = Field(description="Overall summary")
    tables: List[TableProcessingResult] = Field(description="Per-table results")


class EventProcessingResult(BaseModel):
    """Result for processing a single event."""

    ticker: str
    event_date: str
    source: str
    source_id: str
    status: str = Field(description="success, partial, or failed")
    quantitative: Optional[Dict[str, Any]] = None
    qualitative: Optional[Dict[str, Any]] = None
    position: Optional[Dict[str, str]] = None
    disparity: Optional[Dict[str, float]] = None
    error: Optional[str] = None
    errorCode: Optional[str] = None


class BackfillEventsTableResponse(BaseModel):
    """Response for POST /backfillEventsTable endpoint."""

    reqId: str = Field(description="Request unique identifier")
    endpoint: str = Field(default="POST /backfillEventsTable", description="API endpoint")
    overwrite: bool = Field(description="Whether overwrite mode was used")
    summary: Dict[str, Any] = Field(description="Overall summary")
    results: List[EventProcessingResult] = Field(description="Per-event results")


class AnalystGroupResult(BaseModel):
    """Result for a single analyst group."""

    analyst_name: Optional[str]
    analyst_company: Optional[str]
    status: str = Field(description="success, failed, or skipped")
    eventsCount: Optional[int] = None
    performanceSummary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    errorCode: Optional[str] = None


class FillAnalystResponse(BaseModel):
    """Response for POST /fillAnalyst endpoint."""

    reqId: str = Field(description="Request unique identifier")
    endpoint: str = Field(default="POST /fillAnalyst", description="API endpoint")
    summary: Dict[str, Any] = Field(description="Overall summary")
    groups: List[AnalystGroupResult] = Field(description="Per-group results")
