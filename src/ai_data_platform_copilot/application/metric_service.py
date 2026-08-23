"""Governed metric discovery, compilation, lineage, and impact use cases."""

from __future__ import annotations

import re

from ai_data_platform_copilot.domain.errors import MetricExecutionError
from ai_data_platform_copilot.domain.metrics import (
    MetricExecutionRequest,
    MetricExecutionResult,
    MetricImpactResponse,
    MetricLineageEdge,
    MetricLineageNode,
    MetricLineageNodeType,
    MetricLineageResponse,
)
from ai_data_platform_copilot.domain.models import Certainty, EvidenceRef
from ai_data_platform_copilot.ports.metric_executor import MetricExecutor
from ai_data_platform_copilot.ports.semantic_provider import SemanticProvider

_SIMPLE_COLUMN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class MetricService:
    def __init__(self, provider: SemanticProvider, executor: MetricExecutor | None = None) -> None:
        self.provider = provider
        self._executor = executor

    def execute(self, request: MetricExecutionRequest) -> MetricExecutionResult:
        if self._executor is None:
            raise MetricExecutionError("Demo metric execution is disabled")
        if request.query.filters:
            raise MetricExecutionError("Phase 3.1 execution does not accept free-form metric filters")
        compilation = self.provider.compile_metric_query(request.query)
        result = self._executor.execute(compilation)
        return result.model_copy(update={"interpretation": self._interpret_metric_time_nulls(result)})

    def _interpret_metric_time_nulls(self, result: MetricExecutionResult) -> str | None:
        """Explain a null time bucket using executed rows and governed semantic metadata."""
        time_groupings = [
            value for value in result.compilation.request.group_by if value.startswith("metric_time__")
        ]
        metric_name = result.compilation.request.metric
        if len(time_groupings) != 1 or metric_name not in result.columns:
            return None
        time_column = time_groupings[0]
        null_values: list[int | float] = []
        non_null_values: list[int | float] = []
        for row in result.rows:
            value = row.get(metric_name)
            if not isinstance(value, int | float):
                continue
            if row.get(time_column) is None:
                null_values.append(value)
            else:
                non_null_values.append(value)
        if len(null_values) != 1 or not isinstance(null_values[0], int | float):
            return None
        metric = self.provider.get_metric_details(metric_name)
        semantic_model = self.provider.get_semantic_model_details(metric.semantic_model)
        default_dimension = next(
            (
                dimension
                for dimension in semantic_model.dimensions
                if dimension.name == semantic_model.default_time_dimension
            ),
            None,
        )
        if default_dimension is None:
            return None
        null_count = null_values[0]
        dated_count = sum(non_null_values)
        description = default_dimension.description.rstrip(".")
        cause = f" {description}." if description else ""
        return (
            f"The {null_count:g} {metric.label.casefold()} are not missing. They are in the NULL "
            f"`{time_column}` bucket because `{default_dimension.expression}` is NULL. The governed "
            f"metric uses `{default_dimension.name}` (mapped to `{default_dimension.expression}`) as its "
            f"default metric time.{cause} {dated_count:g} {metric.label.casefold()} have a non-null "
            f"`{time_column}` value."
        )

    def lineage(self, metric_name: str) -> MetricLineageResponse:
        metric = self.provider.get_metric_details(metric_name)
        semantic_model = self.provider.get_semantic_model_details(metric.semantic_model)
        measure = next(item for item in semantic_model.measures if item.name == metric.measure)
        evidence = semantic_model.evidence[0]
        model_id = semantic_model.dbt_model_unique_id
        semantic_id = semantic_model.unique_id
        measure_id = f"measure.{semantic_model.name}.{measure.name}"
        column_id = f"column.{semantic_model.dbt_model_name}.{measure.expression}"
        nodes = [
            MetricLineageNode(
                id=model_id,
                name=semantic_model.dbt_model_name,
                node_type=MetricLineageNodeType.DBT_MODEL,
                evidence=evidence,
            ),
            MetricLineageNode(
                id=semantic_id,
                name=semantic_model.name,
                node_type=MetricLineageNodeType.SEMANTIC_MODEL,
                evidence=evidence,
            ),
            MetricLineageNode(
                id=measure_id, name=measure.name, node_type=MetricLineageNodeType.MEASURE, evidence=evidence
            ),
            MetricLineageNode(
                id=metric.unique_id,
                name=metric.name,
                node_type=MetricLineageNodeType.METRIC,
                evidence=metric.evidence[0],
            ),
        ]
        edges = [
            MetricLineageEdge(source=model_id, target=semantic_id, certainty=Certainty.CONFIRMED, evidence=evidence),
            MetricLineageEdge(source=semantic_id, target=measure_id, certainty=Certainty.CONFIRMED, evidence=evidence),
            MetricLineageEdge(
                source=measure_id, target=metric.unique_id, certainty=Certainty.CONFIRMED, evidence=metric.evidence[0]
            ),
        ]
        if measure.expression:
            certainty = Certainty.CONFIRMED if _SIMPLE_COLUMN.fullmatch(measure.expression) else Certainty.INFERRED
            nodes.insert(
                1,
                MetricLineageNode(
                    id=column_id, name=measure.expression, node_type=MetricLineageNodeType.COLUMN, evidence=evidence
                ),
            )
            edges.insert(
                0, MetricLineageEdge(source=column_id, target=model_id, certainty=certainty, evidence=evidence)
            )
        return MetricLineageResponse(metric=metric, nodes=tuple(nodes), edges=tuple(edges))

    def impact(self, model_selector: str) -> MetricImpactResponse:
        normalized = model_selector.casefold().removeprefix("model.")
        matches = tuple(
            metric
            for metric in self.provider.list_metrics()
            if self.provider.get_semantic_model_details(metric.semantic_model).dbt_model_name.casefold() == normalized
            or self.provider.get_semantic_model_details(metric.semantic_model).dbt_model_unique_id.casefold()
            == model_selector.casefold()
        )
        evidence: tuple[EvidenceRef, ...] = tuple(item for metric in matches for item in metric.evidence)
        return MetricImpactResponse(model_selector=model_selector, metrics=matches, evidence=evidence)
