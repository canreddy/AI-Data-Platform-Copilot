"""Governed metric discovery from dbt's generated manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ai_data_platform_copilot.domain.errors import MetricNotFoundError, SemanticModelNotFoundError
from ai_data_platform_copilot.domain.metrics import (
    MetricDefinition,
    MetricQueryCompilation,
    MetricQueryRequest,
    MetricQueryValidation,
    SemanticDimension,
    SemanticMeasure,
    SemanticModel,
)
from ai_data_platform_copilot.domain.models import EvidenceRef


class ArtifactSemanticProvider:
    """Read semantic definitions from dbt's authoritative manifest artifact."""

    def __init__(self, artifact_directory: Path) -> None:
        manifest_path = artifact_directory / "manifest.json"
        raw = manifest_path.read_bytes()
        self._manifest = json.loads(raw)
        self._snapshot_id = hashlib.sha256(raw).hexdigest()[:16]
        self._models = self._parse_models(self._manifest.get("semantic_models", {}))
        self._metrics = self._parse_metrics(self._manifest.get("metrics", {}))

    def list_metrics(self) -> tuple[MetricDefinition, ...]:
        return tuple(sorted(self._metrics.values(), key=lambda metric: metric.name))

    def get_metric_details(self, name: str) -> MetricDefinition:
        try:
            return self._metrics[name.casefold()]
        except KeyError as error:
            raise MetricNotFoundError(f"Governed metric '{name}' was not found") from error

    def list_metric_dimensions(self, name: str) -> tuple[str, ...]:
        metric = self.get_metric_details(name)
        dimensions = [dimension.name for dimension in metric.dimensions]
        if any(dimension.type == "time" for dimension in metric.dimensions):
            dimensions.extend(f"metric_time__{grain}" for grain in ("day", "week", "month", "quarter", "year"))
        return tuple(dict.fromkeys(dimensions))

    def list_semantic_models(self) -> tuple[SemanticModel, ...]:
        return tuple(sorted(self._models.values(), key=lambda model: model.name))

    def get_semantic_model_details(self, name: str) -> SemanticModel:
        try:
            return self._models[name.casefold()]
        except KeyError as error:
            raise SemanticModelNotFoundError(f"Semantic model '{name}' was not found") from error

    def validate_metric_query(self, request: MetricQueryRequest) -> MetricQueryValidation:
        metric = self.get_metric_details(request.metric)
        available = set(self.list_metric_dimensions(metric.name))
        invalid = tuple(value for value in request.group_by if value not in available)
        available_text = ", ".join(sorted(available))
        errors = tuple(
            f"Dimension '{value}' is not compatible with metric '{metric.name}'. Available: {available_text}"
            for value in invalid
        )
        return MetricQueryValidation(
            valid=not errors,
            errors=errors,
            normalized_group_by=request.group_by,
            evidence=metric.evidence,
        )

    def compile_metric_query(self, request: MetricQueryRequest) -> MetricQueryCompilation:
        raise NotImplementedError("ArtifactSemanticProvider discovers and validates metadata but cannot compile SQL")

    def _parse_models(self, values: dict[str, dict[str, Any]]) -> dict[str, SemanticModel]:
        models: dict[str, SemanticModel] = {}
        for unique_id, value in values.items():
            dependencies = value.get("depends_on", {}).get("nodes", [])
            dbt_unique_id = next((item for item in dependencies if item.startswith("model.")), "")
            file_path = value.get("original_file_path")
            evidence = EvidenceRef(
                snapshot_id=self._snapshot_id,
                unique_id=unique_id,
                artifact="manifest.json",
                field=f"semantic_models.{unique_id}",
                file_path=file_path,
            )
            model = SemanticModel(
                unique_id=unique_id,
                name=value["name"],
                description=value.get("description") or "",
                dbt_model_unique_id=dbt_unique_id,
                dbt_model_name=dbt_unique_id.rsplit(".", 1)[-1],
                primary_entity=next(
                    (item["name"] for item in value.get("entities", []) if item.get("type") == "primary"),
                    "",
                ),
                default_time_dimension=(value.get("defaults") or {}).get("agg_time_dimension"),
                dimensions=tuple(
                    SemanticDimension(
                        name=item["name"],
                        type=item["type"],
                        expression=item.get("expr") or item["name"],
                        description=item.get("description") or "",
                        time_granularity=(item.get("type_params") or {}).get("time_granularity"),
                    )
                    for item in value.get("dimensions", [])
                ),
                measures=tuple(
                    SemanticMeasure(
                        name=item["name"],
                        aggregation=item["agg"],
                        expression=item.get("expr") or item["name"],
                        description=item.get("description") or "",
                    )
                    for item in value.get("measures", [])
                ),
                evidence=(evidence,),
            )
            models[model.name.casefold()] = model
        return models

    def _parse_metrics(self, values: dict[str, dict[str, Any]]) -> dict[str, MetricDefinition]:
        metrics: dict[str, MetricDefinition] = {}
        for unique_id, value in values.items():
            measure = (value.get("type_params", {}).get("measure") or {}).get("name", "")
            semantic_model = next(
                (model for model in self._models.values() if any(item.name == measure for item in model.measures)),
                None,
            )
            if semantic_model is None:
                continue
            evidence = EvidenceRef(
                snapshot_id=self._snapshot_id,
                unique_id=unique_id,
                artifact="manifest.json",
                field=f"metrics.{unique_id}",
                file_path=value.get("original_file_path"),
            )
            metric = MetricDefinition(
                unique_id=unique_id,
                name=value["name"],
                label=value.get("label") or value["name"],
                description=value.get("description") or "",
                type=value["type"],
                measure=measure,
                semantic_model=semantic_model.name,
                dimensions=semantic_model.dimensions,
                evidence=(evidence, *semantic_model.evidence),
            )
            metrics[metric.name.casefold()] = metric
        return metrics
