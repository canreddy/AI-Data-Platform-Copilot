"""Guarded compile-only MetricFlow CLI adapter."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import sqlglot
from sqlglot import expressions

from ai_data_platform_copilot.adapters.dbt.semantic import ArtifactSemanticProvider
from ai_data_platform_copilot.domain.errors import MetricFlowCapabilityError
from ai_data_platform_copilot.domain.metrics import (
    MetricDefinition,
    MetricQueryCompilation,
    MetricQueryRequest,
    MetricQueryValidation,
    SemanticModel,
)

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_PROHIBITED = (
    expressions.Insert,
    expressions.Update,
    expressions.Delete,
    expressions.Create,
    expressions.Drop,
    expressions.Command,
)


class MetricFlowProvider:
    """Delegate discovery to artifacts and compile via a fixed MetricFlow executable."""

    def __init__(
        self,
        artifacts: ArtifactSemanticProvider,
        *,
        project_directory: Path,
        executable: Path,
        timeout_seconds: int = 30,
    ) -> None:
        self._artifacts = artifacts
        self._project_directory = project_directory
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    def list_metrics(self) -> tuple[MetricDefinition, ...]:
        return self._artifacts.list_metrics()

    def get_metric_details(self, name: str) -> MetricDefinition:
        return self._artifacts.get_metric_details(name)

    def list_metric_dimensions(self, name: str) -> tuple[str, ...]:
        return self._artifacts.list_metric_dimensions(name)

    def list_semantic_models(self) -> tuple[SemanticModel, ...]:
        return self._artifacts.list_semantic_models()

    def get_semantic_model_details(self, name: str) -> SemanticModel:
        return self._artifacts.get_semantic_model_details(name)

    def validate_metric_query(self, request: MetricQueryRequest) -> MetricQueryValidation:
        return self._artifacts.validate_metric_query(request)

    def compile_metric_query(self, request: MetricQueryRequest) -> MetricQueryCompilation:
        validation = self.validate_metric_query(request)
        if not validation.valid:
            return MetricQueryCompilation(request=request, validation=validation, sql="", evidence=validation.evidence)
        command = [str(self._executable), "query", "--metrics", request.metric]
        if request.group_by:
            command.extend(("--group-by", ",".join(self._metricflow_group_by(request))))
        if request.start_time is not None:
            command.extend(("--start-time", request.start_time.isoformat()))
        if request.end_time is not None:
            command.extend(("--end-time", request.end_time.isoformat()))
        for filter_expression in request.filters:
            command.extend(("--where", filter_expression))
        command.extend(("--explain", "--quiet"))
        try:
            result = subprocess.run(
                command,
                cwd=self._project_directory,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            raise MetricFlowCapabilityError(f"MetricFlow compilation is unavailable: {type(error).__name__}") from error
        if result.returncode != 0:
            message = _ANSI.sub("", result.stderr or result.stdout).strip().splitlines()
            detail = message[-1] if message else "unknown MetricFlow error"
            raise MetricFlowCapabilityError(f"MetricFlow rejected the query: {detail}")
        sql = _ANSI.sub("", result.stdout).strip()
        self._assert_read_only_query(sql)
        return MetricQueryCompilation(
            request=request,
            validation=validation,
            sql=sql,
            evidence=validation.evidence,
        )

    def _metricflow_group_by(self, request: MetricQueryRequest) -> tuple[str, ...]:
        """Translate public artifact dimension names to MetricFlow query identifiers."""
        metric = self._artifacts.get_metric_details(request.metric)
        semantic_model = self._artifacts.get_semantic_model_details(metric.semantic_model)
        dimensions = {dimension.name: dimension for dimension in metric.dimensions}
        translated: list[str] = []
        for value in request.group_by:
            if value.startswith("metric_time__"):
                translated.append(value)
                continue
            dimension = dimensions[value]
            suffix = f"__{dimension.time_granularity}" if dimension.type == "time" else ""
            translated.append(f"{semantic_model.primary_entity}__{value}{suffix}")
        return tuple(translated)

    @staticmethod
    def _assert_read_only_query(sql: str) -> None:
        try:
            statements = sqlglot.parse(sql, read="duckdb")
        except sqlglot.errors.ParseError as error:
            raise MetricFlowCapabilityError("MetricFlow returned SQL that could not be validated") from error
        if len(statements) != 1 or not isinstance(statements[0], expressions.Query):
            raise MetricFlowCapabilityError("MetricFlow must return exactly one read-only query")
        if any(statements[0].find(kind) is not None for kind in _PROHIBITED):
            raise MetricFlowCapabilityError("MetricFlow returned a prohibited SQL statement")
