"""Contracts for optional evidence-backed natural-language orchestration."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai_data_platform_copilot.domain.metrics import MetricQueryRequest


class CopilotIntent(StrEnum):
    METADATA_SEARCH = "metadata_search"
    METRIC_LIST = "metric_list"
    METRIC_DETAILS = "metric_details"
    METRIC_DIMENSIONS = "metric_dimensions"
    METRIC_COMPILE = "metric_compile"
    METRIC_IMPACT = "metric_impact"
    UNSUPPORTED = "unsupported"


class IntentDecision(BaseModel):
    model_config = ConfigDict(frozen=True)
    intent: CopilotIntent
    search_query: str | None = None
    metric: str | None = None
    model: str | None = None
    group_by: tuple[str, ...] = ()
    year: int | None = Field(default=None, ge=1900, le=2200)


class ChatRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    question: str = Field(min_length=1, max_length=1000)


class ToolActivity(BaseModel):
    model_config = ConfigDict(frozen=True)
    tool: str
    status: str


class ChatResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    intent: CopilotIntent
    tool_activity: tuple[ToolActivity, ...]
    evidence: dict[str, Any]
    limitations: tuple[str, ...] = ()
    confirmation_required: bool = False
    execution_query: MetricQueryRequest | None = None
