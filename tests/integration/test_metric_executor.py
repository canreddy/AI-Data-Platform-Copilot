from pathlib import Path

import pytest

from ai_data_platform_copilot.adapters.duckdb.metric_executor import DuckDBDemoMetricExecutor
from ai_data_platform_copilot.domain.errors import MetricExecutionError
from ai_data_platform_copilot.domain.metrics import (
    MetricQueryCompilation,
    MetricQueryRequest,
    MetricQueryValidation,
)

ROOT = Path(__file__).resolve().parents[2]


def compilation(sql: str) -> MetricQueryCompilation:
    request = MetricQueryRequest(metric="total_revenue")
    return MetricQueryCompilation(
        request=request,
        validation=MetricQueryValidation(valid=True),
        sql=sql,
    )


def test_executor_returns_bounded_rows_from_read_only_demo() -> None:
    executor = DuckDBDemoMetricExecutor(
        database_path=ROOT / "demo" / "jaffle_shop" / "jaffle_shop.duckdb",
        max_rows=10,
    )
    result = executor.execute(compilation("select sum(amount) as total_revenue from payments"))

    assert result.executed is True
    assert result.connection_mode == "read_only"
    assert result.row_count == 1
    assert result.rows[0]["total_revenue"] is not None


def test_executor_rejects_mutation_before_opening_database() -> None:
    executor = DuckDBDemoMetricExecutor(database_path=ROOT / "demo" / "jaffle_shop" / "jaffle_shop.duckdb")
    with pytest.raises(MetricExecutionError, match="exactly one read-only query"):
        executor.execute(compilation("drop table payments"))
