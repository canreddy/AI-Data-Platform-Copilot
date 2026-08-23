from pathlib import Path

from fastapi.testclient import TestClient

from ai_data_platform_copilot.api.app import create_app
from ai_data_platform_copilot.settings import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_phase_one_api_demonstrations(tmp_path: Path) -> None:
    settings = Settings(
        metadata_database_path=tmp_path / "metadata.sqlite3",
        artifact_directory=ROOT / "demo" / "jaffle_shop" / "target",
        auto_ingest=True,
    )

    with TestClient(create_app(settings)) as client:
        ready = client.get("/health/ready")
        orders = client.get("/api/v1/metadata/search", params={"q": "orders"})
        customer_id = client.get("/api/v1/metadata/search", params={"q": "customer_id"})
        upstream = client.get("/api/v1/lineage/customers", params={"direction": "upstream", "max_depth": 1})
        downstream = client.get("/api/v1/lineage/stg_orders", params={"direction": "downstream", "max_depth": 1})

    assert ready.status_code == 200
    assert orders.status_code == 200
    assert orders.json()["results"][0]["resource"]["name"] == "orders"
    assert any("customer_id" in result["matched_columns"] for result in customer_id.json()["results"])
    assert {node["name"] for node in upstream.json()["nodes"]} == {
        "customers",
        "stg_customers",
        "stg_orders",
        "stg_payments",
    }
    assert {node["name"] for node in downstream.json()["nodes"]} == {
        "stg_orders",
        "customers",
        "orders",
        "payments",
    }
    assert "x-request-id" in downstream.headers


def test_ingest_is_idempotent_and_missing_resource_is_structured(tmp_path: Path) -> None:
    settings = Settings(
        metadata_database_path=tmp_path / "metadata.sqlite3",
        artifact_directory=ROOT / "demo" / "jaffle_shop" / "target",
        auto_ingest=True,
    )

    with TestClient(create_app(settings)) as client:
        ingestion = client.post("/api/v1/artifacts/ingest")
        missing = client.get("/api/v1/models/not_a_model")

    assert ingestion.status_code == 200
    assert ingestion.json()["created"] is False
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "resource_not_found"
