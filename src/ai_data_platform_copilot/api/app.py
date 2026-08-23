"""FastAPI application for deterministic Phase 1 capabilities."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import RequestResponseEndpoint

from ai_data_platform_copilot.adapters.dbt.artifacts import load_artifact_snapshot
from ai_data_platform_copilot.adapters.dbt.semantic import ArtifactSemanticProvider
from ai_data_platform_copilot.adapters.duckdb.metric_executor import DuckDBDemoMetricExecutor
from ai_data_platform_copilot.adapters.metricflow.provider import MetricFlowProvider
from ai_data_platform_copilot.adapters.openai.chat import OpenAIChatProvider
from ai_data_platform_copilot.adapters.openai.sql_explanation import OpenAISQLExplanationProvider
from ai_data_platform_copilot.adapters.sqlite.repository import SQLiteMetadataRepository
from ai_data_platform_copilot.application.chat_service import ChatService
from ai_data_platform_copilot.application.metric_service import MetricService
from ai_data_platform_copilot.application.services import LineageService, MetadataService
from ai_data_platform_copilot.domain.chat import ChatRequest, ChatResponse
from ai_data_platform_copilot.domain.errors import (
    AmbiguousResourceError,
    CopilotError,
    MetricExecutionError,
    MetricFlowCapabilityError,
    MetricNotFoundError,
    ResourceNotFoundError,
    SemanticModelNotFoundError,
    SnapshotNotFoundError,
)
from ai_data_platform_copilot.domain.metrics import (
    MetricDefinition,
    MetricExecutionRequest,
    MetricExecutionResult,
    MetricImpactResponse,
    MetricLineageResponse,
    MetricQueryCompilation,
    MetricQueryRequest,
    MetricQueryValidation,
    SemanticModel,
)
from ai_data_platform_copilot.domain.models import (
    ImpactResponse,
    IngestResponse,
    LineageResponse,
    MetadataResource,
    ResourceType,
    SearchResponse,
    SnapshotInfo,
)
from ai_data_platform_copilot.domain.sql_review import SQLReviewRequest, SQLReviewResponse
from ai_data_platform_copilot.settings import Settings
from ai_data_platform_copilot.sql_review.analyzer import SQLReviewService

logger = logging.getLogger("ai_data_platform_copilot")


@dataclass(frozen=True)
class Container:
    """Explicit application dependency container."""

    settings: Settings
    repository: SQLiteMetadataRepository
    metadata: MetadataService
    lineage: LineageService
    sql_review: SQLReviewService
    metrics: MetricService
    chat: ChatService | None


def create_container(settings: Settings) -> Container:
    repository = SQLiteMetadataRepository(settings.metadata_database_path)
    explanation_provider = (
        OpenAISQLExplanationProvider(api_key=settings.openai_api_key, model=settings.openai_model)
        if settings.openai_api_key
        else None
    )
    artifact_semantics = ArtifactSemanticProvider(settings.artifact_directory)
    semantic_provider = MetricFlowProvider(
        artifact_semantics,
        project_directory=settings.dbt_project_directory,
        executable=settings.metricflow_executable,
    )
    metric_executor = (
        DuckDBDemoMetricExecutor(database_path=settings.dbt_project_directory / "jaffle_shop.duckdb")
        if settings.metric_execution_enabled
        else None
    )
    metadata_service = MetadataService(repository)
    metric_service = MetricService(semantic_provider, metric_executor)
    chat_service = (
        ChatService(
            OpenAIChatProvider(api_key=settings.openai_api_key, model=settings.openai_model),
            metadata_service,
            metric_service,
        )
        if settings.openai_api_key
        else None
    )
    return Container(
        settings=settings,
        repository=repository,
        metadata=metadata_service,
        lineage=LineageService(repository),
        sql_review=SQLReviewService(repository, explanation_provider=explanation_provider),
        metrics=metric_service,
        chat=chat_service,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an independently testable application instance."""
    resolved_settings = settings or Settings.from_environment()
    container = create_container(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if resolved_settings.auto_ingest and (resolved_settings.artifact_directory / "manifest.json").is_file():
            snapshot = load_artifact_snapshot(resolved_settings.artifact_directory)
            container.repository.ingest(snapshot)
        yield

    app = FastAPI(
        title="AI Data Platform Copilot",
        version="0.1.0",
        description="Deterministic, evidence-backed dbt metadata and lineage APIs.",
        lifespan=lifespan,
    )
    app.state.container = container

    @app.middleware("http")
    async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        logger.info(
            json.dumps(
                {
                    "event": "request_completed",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )
        )
        return response

    @app.exception_handler(CopilotError)
    async def copilot_error_handler(request: Request, error: CopilotError) -> JSONResponse:
        status = 400
        if isinstance(
            error, ResourceNotFoundError | SnapshotNotFoundError | MetricNotFoundError | SemanticModelNotFoundError
        ):
            status = 404
        elif isinstance(error, AmbiguousResourceError):
            status = 409
        elif isinstance(error, MetricFlowCapabilityError):
            status = 503
        elif isinstance(error, MetricExecutionError):
            status = 422
        return JSONResponse(
            status_code=status,
            content={
                "error": {"code": error.code, "message": str(error)},
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.get("/health/live")
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def readiness() -> dict[str, str]:
        snapshot = container.repository.active_snapshot()
        return {"status": "ready", "snapshot_id": snapshot.snapshot_id}

    @app.post("/api/v1/artifacts/ingest", response_model=IngestResponse)
    def ingest_artifacts() -> IngestResponse:
        started = time.perf_counter()
        snapshot = load_artifact_snapshot(container.settings.artifact_directory)
        info, created = container.repository.ingest(snapshot)
        return IngestResponse(
            snapshot=info,
            created=created,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    @app.get("/api/v1/artifacts/active", response_model=SnapshotInfo)
    def active_snapshot() -> SnapshotInfo:
        return container.repository.active_snapshot()

    @app.get("/api/v1/metadata/search", response_model=SearchResponse)
    def search_metadata(
        q: Annotated[str, Query(min_length=1, max_length=200)],
        resource_type: Annotated[list[ResourceType] | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        snapshot_id: str | None = None,
    ) -> SearchResponse:
        return container.metadata.search(
            q,
            resource_types=resource_type or (),
            limit=limit,
            snapshot_id=snapshot_id,
        )

    @app.get("/api/v1/models/{selector:path}", response_model=MetadataResource)
    def model_details(
        selector: str,
        snapshot_id: str | None = None,
    ) -> MetadataResource:
        return container.metadata.details(selector, snapshot_id=snapshot_id)

    @app.get("/api/v1/lineage/{selector:path}", response_model=LineageResponse)
    def lineage(
        selector: str,
        direction: Annotated[str, Query(pattern="^(upstream|downstream|both)$")] = "both",
        max_depth: Annotated[int, Query(ge=0, le=20)] = 5,
        snapshot_id: str | None = None,
    ) -> LineageResponse:
        return container.lineage.lineage(
            selector,
            direction=direction,
            max_depth=max_depth,
            snapshot_id=snapshot_id,
        )

    @app.get("/api/v1/impact/{selector:path}", response_model=ImpactResponse)
    def impact(
        selector: str,
        max_depth: Annotated[int, Query(ge=0, le=20)] = 10,
        snapshot_id: str | None = None,
    ) -> ImpactResponse:
        return container.lineage.impact(selector, max_depth=max_depth, snapshot_id=snapshot_id)

    @app.post("/api/v1/sql/reviews", response_model=SQLReviewResponse)
    def review_sql(review_request: SQLReviewRequest) -> SQLReviewResponse:
        return container.sql_review.review(review_request)

    @app.get("/api/v1/capabilities")
    def capabilities() -> dict[str, bool]:
        return {
            "metadata": True,
            "lineage": True,
            "sql_review": True,
            "metric_discovery": True,
            "metricflow_compilation": container.settings.metricflow_executable.is_file(),
            "demo_metric_execution": container.settings.metric_execution_enabled
            and (container.settings.dbt_project_directory / "jaffle_shop.duckdb").is_file(),
            "copilot_chat": bool(container.settings.openai_api_key),
        }

    @app.get("/api/v1/metrics", response_model=list[MetricDefinition])
    def list_metrics() -> tuple[MetricDefinition, ...]:
        return container.metrics.provider.list_metrics()

    @app.get("/api/v1/metrics/impact/{model_selector:path}", response_model=MetricImpactResponse)
    def metric_impact(model_selector: str) -> MetricImpactResponse:
        return container.metrics.impact(model_selector)

    @app.get("/api/v1/metrics/{name}/dimensions", response_model=list[str])
    def metric_dimensions(name: str) -> tuple[str, ...]:
        return container.metrics.provider.list_metric_dimensions(name)

    @app.get("/api/v1/metrics/{name}/lineage", response_model=MetricLineageResponse)
    def metric_lineage(name: str) -> MetricLineageResponse:
        return container.metrics.lineage(name)

    @app.get("/api/v1/metrics/{name}", response_model=MetricDefinition)
    def metric_details(name: str) -> MetricDefinition:
        return container.metrics.provider.get_metric_details(name)

    @app.get("/api/v1/semantic-models", response_model=list[SemanticModel])
    def list_semantic_models() -> tuple[SemanticModel, ...]:
        return container.metrics.provider.list_semantic_models()

    @app.get("/api/v1/semantic-models/{name}", response_model=SemanticModel)
    def semantic_model_details(name: str) -> SemanticModel:
        return container.metrics.provider.get_semantic_model_details(name)

    @app.post("/api/v1/metric-queries/validate", response_model=MetricQueryValidation)
    def validate_metric_query(query: MetricQueryRequest) -> MetricQueryValidation:
        return container.metrics.provider.validate_metric_query(query)

    @app.post("/api/v1/metric-queries/compile", response_model=MetricQueryCompilation)
    def compile_metric_query(query: MetricQueryRequest) -> MetricQueryCompilation:
        return container.metrics.provider.compile_metric_query(query)

    @app.post("/api/v1/metric-queries/execute", response_model=MetricExecutionResult)
    def execute_metric_query(execution_request: MetricExecutionRequest) -> MetricExecutionResult:
        return container.metrics.execute(execution_request)

    @app.post("/api/v1/chat", response_model=ChatResponse)
    def chat(chat_request: ChatRequest) -> ChatResponse:
        if container.chat is None:
            raise HTTPException(
                status_code=503,
                detail={"code": "chat_disabled", "message": "Set OPENAI_API_KEY to enable optional Copilot chat."},
            )
        return container.chat.ask(chat_request.question)

    return app
