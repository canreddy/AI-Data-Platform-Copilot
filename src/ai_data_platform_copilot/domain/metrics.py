"""Governed semantic-layer contracts used by artifact and MetricFlow adapters."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_data_platform_copilot.domain.models import Certainty, EvidenceRef


class SemanticDimension(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    type: str
    expression: str
    description: str = ""
    time_granularity: str | None = None


class SemanticMeasure(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    aggregation: str
    expression: str
    description: str = ""


class SemanticModel(BaseModel):
    model_config = ConfigDict(frozen=True)
    unique_id: str
    name: str
    description: str = ""
    dbt_model_unique_id: str
    dbt_model_name: str
    primary_entity: str
    default_time_dimension: str | None = None
    dimensions: tuple[SemanticDimension, ...] = ()
    measures: tuple[SemanticMeasure, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()


class MetricDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    unique_id: str
    name: str
    label: str
    description: str = ""
    type: str
    measure: str
    semantic_model: str
    dimensions: tuple[SemanticDimension, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()


class MetricQueryRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    metric: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    group_by: tuple[str, ...] = ()
    filters: tuple[str, ...] = ()
    start_time: date | None = None
    end_time: date | None = None

    @field_validator("group_by")
    @classmethod
    def validate_group_by(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if (
                not value
                or len(value) > 150
                or not all(character.isalnum() or character in "_-" for character in value)
            ):
                raise ValueError("group_by values may contain only letters, numbers, underscores, and hyphens")
        return values

    @field_validator("filters")
    @classmethod
    def validate_filters(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(len(value) > 500 for value in values):
            raise ValueError("filters must be at most 500 characters")
        return values

    @field_validator("end_time")
    @classmethod
    def validate_time_range(cls, value: date | None, info: Any) -> date | None:
        start_time = info.data.get("start_time")
        if value is not None and start_time is not None and value < start_time:
            raise ValueError("end_time must be on or after start_time")
        return value


class MetricQueryValidation(BaseModel):
    model_config = ConfigDict(frozen=True)
    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    normalized_group_by: tuple[str, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()


class MetricQueryCompilation(BaseModel):
    model_config = ConfigDict(frozen=True)
    request: MetricQueryRequest
    validation: MetricQueryValidation
    sql: str
    provider: str = "metricflow"
    executed: bool = False
    evidence: tuple[EvidenceRef, ...] = ()
    limitations: tuple[str, ...] = ("SQL was compiled but not executed.",)


class MetricExecutionRequest(BaseModel):
    """Server-owned metric request with explicit execution confirmation."""

    model_config = ConfigDict(frozen=True)
    query: MetricQueryRequest
    confirmed: Literal[True]


class MetricExecutionResult(BaseModel):
    """Bounded rows and evidence from the included read-only DuckDB demo."""

    model_config = ConfigDict(frozen=True)
    compilation: MetricQueryCompilation
    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    row_count: int
    truncated: bool
    duration_ms: float
    database: str
    connection_mode: Literal["read_only"] = "read_only"
    executed: Literal[True] = True
    confirmed: Literal[True] = True
    max_rows: int
    timeout_seconds: int
    evidence: tuple[EvidenceRef, ...] = ()
    interpretation: str | None = None


class MetricLineageNodeType(StrEnum):
    DBT_MODEL = "dbt_model"
    SEMANTIC_MODEL = "semantic_model"
    MEASURE = "measure"
    METRIC = "metric"
    COLUMN = "column"


class MetricLineageNode(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    name: str
    node_type: MetricLineageNodeType
    evidence: EvidenceRef


class MetricLineageEdge(BaseModel):
    model_config = ConfigDict(frozen=True)
    source: str
    target: str
    certainty: Certainty
    evidence: EvidenceRef


class MetricLineageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    metric: MetricDefinition
    nodes: tuple[MetricLineageNode, ...]
    edges: tuple[MetricLineageEdge, ...]


class MetricImpactResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    model_selector: str
    metrics: tuple[MetricDefinition, ...]
    evidence: tuple[EvidenceRef, ...]
