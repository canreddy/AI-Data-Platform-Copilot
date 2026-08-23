from pathlib import Path

from ai_data_platform_copilot.adapters.dbt.artifacts import load_artifact_snapshot
from ai_data_platform_copilot.adapters.sqlite.repository import SQLiteMetadataRepository
from ai_data_platform_copilot.application.services import LineageService
from ai_data_platform_copilot.domain.models import Certainty

ROOT = Path(__file__).resolve().parents[2]


def lineage_service(tmp_path: Path) -> LineageService:
    repository = SQLiteMetadataRepository(tmp_path / "metadata.sqlite3")
    repository.ingest(load_artifact_snapshot(ROOT / "demo" / "jaffle_shop" / "target"))
    return LineageService(repository)


def test_customers_upstream_contains_all_referenced_staging_models(tmp_path: Path) -> None:
    result = lineage_service(tmp_path).lineage("customers", direction="upstream", max_depth=1)

    names = {node.name for node in result.nodes}
    assert names == {"customers", "stg_customers", "stg_orders", "stg_payments"}
    assert all(edge.certainty is Certainty.CONFIRMED for edge in result.edges)
    assert all(edge.evidence.field.startswith("parent_map.") for edge in result.edges)


def test_stg_orders_downstream_and_impact(tmp_path: Path) -> None:
    service = lineage_service(tmp_path)

    lineage = service.lineage("stg_orders", direction="downstream", max_depth=1)
    impact = service.impact("stg_orders", max_depth=10)

    assert {node.name for node in lineage.nodes} == {"stg_orders", "customers", "orders", "payments"}
    assert impact.affected_count == len(impact.nodes) - 1
    assert impact.affected_count >= 3


def test_depth_zero_returns_only_root(tmp_path: Path) -> None:
    result = lineage_service(tmp_path).lineage("orders", direction="both", max_depth=0)

    assert [node.name for node in result.nodes] == ["orders"]
    assert result.edges == ()
