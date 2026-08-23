from pathlib import Path

from ai_data_platform_copilot.adapters.dbt.artifacts import load_artifact_snapshot
from ai_data_platform_copilot.adapters.sqlite.repository import SQLiteMetadataRepository
from ai_data_platform_copilot.domain.models import ResourceType

ROOT = Path(__file__).resolve().parents[2]


def repository_with_snapshot(tmp_path: Path) -> SQLiteMetadataRepository:
    repository = SQLiteMetadataRepository(tmp_path / "metadata.sqlite3")
    snapshot = load_artifact_snapshot(ROOT / "demo" / "jaffle_shop" / "target")
    repository.ingest(snapshot)
    return repository


def test_ingestion_is_idempotent_and_snapshot_is_active(tmp_path: Path) -> None:
    repository = SQLiteMetadataRepository(tmp_path / "metadata.sqlite3")
    snapshot = load_artifact_snapshot(ROOT / "demo" / "jaffle_shop" / "target")

    first, first_created = repository.ingest(snapshot)
    second, second_created = repository.ingest(snapshot)

    assert first_created is True
    assert second_created is False
    assert first.snapshot_id == second.snapshot_id == repository.active_snapshot().snapshot_id
    assert first.resource_count == 10


def test_exact_name_and_exact_column_search(tmp_path: Path) -> None:
    repository = repository_with_snapshot(tmp_path)

    exact_name = repository.search("orders")
    exact_column = repository.search("customer_id")

    assert exact_name[0].resource.name == "orders"
    assert exact_name[0].match_reason == "exact_name"
    assert any(result.match_reason == "exact_column" for result in exact_column)
    assert "customer_id" in exact_column[0].matched_columns


def test_case_insensitive_full_text_and_type_filter(tmp_path: Path) -> None:
    repository = repository_with_snapshot(tmp_path)

    results = repository.search("BASIC INFORMATION", resource_types=[ResourceType.MODEL])

    assert {result.resource.name for result in results} >= {"customers", "orders"}
    assert all(result.resource.resource_type is ResourceType.MODEL for result in results)


def test_resource_contains_stable_evidence_and_catalog_types(tmp_path: Path) -> None:
    repository = repository_with_snapshot(tmp_path)

    resource = repository.get_resource("orders")

    assert resource.unique_id == "model.jaffle_shop.orders"
    assert resource.evidence[0].snapshot_id == repository.active_snapshot().snapshot_id
    assert resource.evidence[0].file_path == "models/orders.sql"
    assert next(column for column in resource.columns if column.name == "order_id").data_type is not None
