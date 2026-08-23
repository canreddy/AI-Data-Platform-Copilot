from pathlib import Path

import pytest

from ai_data_platform_copilot.adapters.dbt.semantic import ArtifactSemanticProvider
from ai_data_platform_copilot.domain.errors import MetricNotFoundError
from ai_data_platform_copilot.domain.metrics import MetricQueryRequest

ROOT = Path(__file__).resolve().parents[2]


def provider() -> ArtifactSemanticProvider:
    return ArtifactSemanticProvider(ROOT / "demo" / "jaffle_shop" / "target")


def test_discovers_governed_metrics_and_evidence() -> None:
    metrics = provider().list_metrics()
    assert {metric.name for metric in metrics} == {"customers", "orders", "total_revenue", "average_order_value"}
    revenue = provider().get_metric_details("total_revenue")
    assert revenue.measure == "total_revenue"
    assert revenue.semantic_model == "payments"
    assert provider().get_semantic_model_details("payments").primary_entity == "payment"
    assert revenue.evidence[0].file_path == "models/semantic_models.yml"


def test_validates_dimension_compatibility_without_compiling() -> None:
    semantic_provider = provider()
    valid = semantic_provider.validate_metric_query(
        MetricQueryRequest(metric="total_revenue", group_by=("metric_time__month", "payment_method"))
    )
    invalid = semantic_provider.validate_metric_query(
        MetricQueryRequest(metric="total_revenue", group_by=("not_a_dimension",))
    )
    assert valid.valid is True
    assert invalid.valid is False
    assert "not_a_dimension" in invalid.errors[0]


def test_undefined_metric_is_reported_honestly() -> None:
    with pytest.raises(MetricNotFoundError):
        provider().get_metric_details("gross_margin")
