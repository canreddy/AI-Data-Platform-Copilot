from pathlib import Path

from ai_data_platform_copilot.adapters.dbt.semantic import ArtifactSemanticProvider
from ai_data_platform_copilot.application.metric_service import MetricService
from ai_data_platform_copilot.domain.metrics import (
    MetricExecutionRequest,
    MetricExecutionResult,
    MetricQueryCompilation,
    MetricQueryRequest,
)

ROOT = Path(__file__).resolve().parents[2]


class CompilingProvider(ArtifactSemanticProvider):
    def compile_metric_query(self, request: MetricQueryRequest) -> MetricQueryCompilation:
        validation = self.validate_metric_query(request)
        return MetricQueryCompilation(
            request=request,
            validation=validation,
            sql="select metric_time__year, customers from governed_result",
            evidence=validation.evidence,
        )


class CustomerYearExecutor:
    def execute(self, compilation: MetricQueryCompilation) -> MetricExecutionResult:
        return MetricExecutionResult(
            compilation=compilation,
            columns=("metric_time__year", "customers"),
            rows=(
                {"metric_time__year": "2018-01-01", "customers": 62},
                {"metric_time__year": None, "customers": 38},
            ),
            row_count=2,
            truncated=False,
            duration_ms=1.0,
            database="demo.duckdb",
            max_rows=100,
            timeout_seconds=5,
            evidence=compilation.evidence,
        )


def test_metric_time_null_bucket_gets_deterministic_semantic_interpretation() -> None:
    provider = CompilingProvider(ROOT / "demo" / "jaffle_shop" / "target")
    service = MetricService(provider, CustomerYearExecutor())

    result = service.execute(
        MetricExecutionRequest(
            query=MetricQueryRequest(metric="customers", group_by=("metric_time__year",)),
            confirmed=True,
        )
    )

    assert result.interpretation is not None
    assert "38 customers are not missing" in result.interpretation
    assert "`first_order` is NULL" in result.interpretation
    assert "customer has no orders" in result.interpretation
    assert "62 customers have a non-null" in result.interpretation
