from pathlib import Path

from fastapi.testclient import TestClient

from ai_data_platform_copilot.api.app import create_app
from ai_data_platform_copilot.settings import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_metric_discovery_validation_lineage_and_disabled_chat(tmp_path: Path) -> None:
    settings = Settings(
        metadata_database_path=tmp_path / "metadata.sqlite3",
        artifact_directory=ROOT / "demo" / "jaffle_shop" / "target",
        auto_ingest=True,
    )
    with TestClient(create_app(settings)) as client:
        metrics = client.get("/api/v1/metrics")
        revenue = client.get("/api/v1/metrics/total_revenue")
        lineage = client.get("/api/v1/metrics/total_revenue/lineage")
        impact = client.get("/api/v1/metrics/impact/payments")
        invalid = client.post(
            "/api/v1/metric-queries/validate",
            json={"metric": "total_revenue", "group_by": ["customer_age"]},
        )
        chat = client.post("/api/v1/chat", json={"question": "What metrics are available?"})
        unconfirmed_execution = client.post(
            "/api/v1/metric-queries/execute",
            json={"query": {"metric": "total_revenue"}, "confirmed": False},
        )
        filtered_execution = client.post(
            "/api/v1/metric-queries/execute",
            json={
                "query": {"metric": "total_revenue", "filters": ["{{ Dimension('order_id') }} > 1"]},
                "confirmed": True,
            },
        )
        confirmed_execution = client.post(
            "/api/v1/metric-queries/execute",
            json={
                "query": {
                    "metric": "total_revenue",
                    "start_time": "2018-01-01",
                    "end_time": "2018-12-31",
                },
                "confirmed": True,
            },
        )
    assert metrics.status_code == 200
    assert {item["name"] for item in metrics.json()} >= {"total_revenue", "average_order_value"}
    assert revenue.json()["semantic_model"] == "payments"
    assert {node["node_type"] for node in lineage.json()["nodes"]} == {
        "column",
        "dbt_model",
        "semantic_model",
        "measure",
        "metric",
    }
    assert {metric["name"] for metric in impact.json()["metrics"]} == {"total_revenue"}
    assert invalid.json()["valid"] is False
    assert chat.status_code == 503
    assert unconfirmed_execution.status_code == 422
    assert filtered_execution.status_code == 422
    assert filtered_execution.json()["error"]["code"] == "metric_execution_error"
    assert confirmed_execution.status_code == 200
    assert confirmed_execution.json()["rows"] == [{"total_revenue": 1672.0}]
    assert confirmed_execution.json()["connection_mode"] == "read_only"
