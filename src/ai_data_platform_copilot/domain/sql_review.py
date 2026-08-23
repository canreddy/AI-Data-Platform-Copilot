"""Typed SQL review contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ai_data_platform_copilot.domain.models import EvidenceRef, MetadataResource


class SQLDialect(StrEnum):
    """Explicitly supported SQL dialects."""

    BIGQUERY = "bigquery"
    DUCKDB = "duckdb"


class FindingSeverity(StrEnum):
    """Finding severity ordered from informational to blocking."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class FindingCategory(StrEnum):
    """Review concern addressed by a finding."""

    SAFETY = "safety"
    CORRECTNESS = "correctness"
    PERFORMANCE = "performance"
    COST = "cost"
    MAINTAINABILITY = "maintainability"


class SQLReviewRequest(BaseModel):
    """SQL submitted for static analysis only."""

    model_config = ConfigDict(frozen=True)

    sql: str = Field(min_length=1, max_length=100_000)
    dialect: SQLDialect = SQLDialect.BIGQUERY
    snapshot_id: str | None = None
    governed_metric_sql: bool = False
    include_explanation: bool = False


class ExplanationStatus(StrEnum):
    """State of the optional LLM explanation."""

    NOT_REQUESTED = "not_requested"
    DISABLED = "disabled"
    GENERATED = "generated"
    ERROR = "error"


class SQLExplanation(BaseModel):
    """Optional prose derived only from deterministic findings."""

    model_config = ConfigDict(frozen=True)

    text: str
    model: str
    response_id: str
    based_on_rule_ids: tuple[str, ...]
    input_tokens: int | None = None
    output_tokens: int | None = None


class SQLFinding(BaseModel):
    """One deterministic SQL review result."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    severity: FindingSeverity
    category: FindingCategory
    title: str
    message: str
    recommendation: str
    statement_index: int
    line: int | None = None
    column: int | None = None
    evidence: tuple[EvidenceRef, ...] = ()


class SQLReviewSummary(BaseModel):
    """Finding counts for quick rendering."""

    model_config = ConfigDict(frozen=True)

    critical: int = 0
    error: int = 0
    warning: int = 0
    info: int = 0


class SQLReviewResponse(BaseModel):
    """Complete deterministic SQL review response."""

    model_config = ConfigDict(frozen=True)

    dialect: SQLDialect
    valid_sql: bool
    read_only: bool
    statement_count: int
    findings: tuple[SQLFinding, ...]
    summary: SQLReviewSummary
    referenced_resources: tuple[MetadataResource, ...] = ()
    metadata_snapshot_id: str | None = None
    limitations: tuple[str, ...] = ()
    governed_metric_sql: bool = False
    explanation_status: ExplanationStatus = ExplanationStatus.NOT_REQUESTED
    explanation: SQLExplanation | None = None
    duration_ms: float
