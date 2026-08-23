from datetime import date
from pathlib import Path
from unittest.mock import patch

from ai_data_platform_copilot.adapters.dbt.semantic import ArtifactSemanticProvider
from ai_data_platform_copilot.adapters.metricflow.provider import MetricFlowProvider
from ai_data_platform_copilot.domain.metrics import MetricQueryRequest

ROOT = Path(__file__).resolve().parents[2]


def test_compilation_uses_fixed_argument_array_and_never_executes_sql() -> None:
    artifacts = ArtifactSemanticProvider(ROOT / "demo" / "jaffle_shop" / "target")
    provider = MetricFlowProvider(
        artifacts,
        project_directory=ROOT / "demo" / "jaffle_shop",
        executable=Path("/fixed/mf"),
    )
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "select 1 as total_revenue"
        run.return_value.stderr = ""
        result = provider.compile_metric_query(
            MetricQueryRequest(
                metric="total_revenue",
                group_by=("metric_time__month",),
                start_time=date(2018, 1, 1),
                end_time=date(2018, 12, 31),
            )
        )
    command = run.call_args.args[0]
    assert command == [
        "/fixed/mf",
        "query",
        "--metrics",
        "total_revenue",
        "--group-by",
        "metric_time__month",
        "--start-time",
        "2018-01-01",
        "--end-time",
        "2018-12-31",
        "--explain",
        "--quiet",
    ]
    assert result.executed is False
    assert result.sql == "select 1 as total_revenue"


def test_compilation_qualifies_public_categorical_dimension_for_metricflow() -> None:
    artifacts = ArtifactSemanticProvider(ROOT / "demo" / "jaffle_shop" / "target")
    provider = MetricFlowProvider(
        artifacts,
        project_directory=ROOT / "demo" / "jaffle_shop",
        executable=Path("/fixed/mf"),
    )
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "select 1 as orders"
        run.return_value.stderr = ""
        provider.compile_metric_query(MetricQueryRequest(metric="orders", group_by=("order_status",)))

    command = run.call_args.args[0]
    assert command[command.index("--group-by") + 1] == "order__order_status"
