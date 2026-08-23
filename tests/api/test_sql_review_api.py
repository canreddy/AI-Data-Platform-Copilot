from pathlib import Path

from fastapi.testclient import TestClient

from ai_data_platform_copilot.api.app import create_app
from ai_data_platform_copilot.settings import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_sql_review_endpoint_is_deterministic_and_metadata_aware(tmp_path: Path) -> None:
    settings = Settings(
        metadata_database_path=tmp_path / "metadata.sqlite3",
        artifact_directory=ROOT / "demo" / "jaffle_shop" / "target",
        auto_ingest=True,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/sql/reviews",
            json={
                "sql": "select o.not_real from orders o",
                "dialect": "bigquery",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["read_only"] is True
    assert {finding["rule_id"] for finding in payload["findings"]} >= {
        "correctness.unknown_qualified_column",
        "cost.bigquery_unbounded_scan",
    }
    assert payload["referenced_resources"][0]["name"] == "orders"
    assert "x-request-id" in response.headers


def test_sql_review_never_executes_destructive_sql(tmp_path: Path) -> None:
    settings = Settings(
        metadata_database_path=tmp_path / "metadata.sqlite3",
        artifact_directory=ROOT / "demo" / "jaffle_shop" / "target",
        auto_ingest=True,
    )

    with TestClient(create_app(settings)) as client:
        before = client.get("/api/v1/models/orders")
        review = client.post(
            "/api/v1/sql/reviews",
            json={"sql": "drop table orders", "dialect": "duckdb"},
        )
        after = client.get("/api/v1/models/orders")

    assert review.status_code == 200
    assert review.json()["read_only"] is False
    assert review.json()["summary"]["critical"] == 1
    assert before.json() == after.json()


def test_sql_review_rejects_unsupported_dialect(tmp_path: Path) -> None:
    settings = Settings(
        metadata_database_path=tmp_path / "metadata.sqlite3",
        artifact_directory=ROOT / "demo" / "jaffle_shop" / "target",
        auto_ingest=False,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/sql/reviews",
            json={"sql": "select 1", "dialect": "snowflake"},
        )

    assert response.status_code == 422


def test_optional_explanation_is_explicitly_disabled_without_api_key(tmp_path: Path) -> None:
    settings = Settings(
        metadata_database_path=tmp_path / "metadata.sqlite3",
        artifact_directory=ROOT / "demo" / "jaffle_shop" / "target",
        auto_ingest=False,
        openai_api_key=None,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/sql/reviews",
            json={"sql": "select 1", "dialect": "bigquery", "include_explanation": True},
        )

    assert response.status_code == 200
    assert response.json()["explanation_status"] == "disabled"
    assert response.json()["explanation"] is None
