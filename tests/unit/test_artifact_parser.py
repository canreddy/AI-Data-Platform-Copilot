import json
from pathlib import Path

import pytest

from ai_data_platform_copilot.adapters.dbt.artifacts import load_artifact_snapshot
from ai_data_platform_copilot.domain.errors import ArtifactError


def test_loads_normalized_jaffle_artifacts() -> None:
    artifact_dir = Path(__file__).resolve().parents[2] / "demo" / "jaffle_shop" / "target"
    snapshot = load_artifact_snapshot(artifact_dir)

    resources = {resource.unique_id: resource for resource in snapshot.resources}
    assert snapshot.dbt_version == "1.11.13"
    assert len(snapshot.snapshot_id) == 64
    assert resources["model.jaffle_shop.orders"].file_path == "models/orders.sql"
    assert "customer_id" in {column.name for column in resources["model.jaffle_shop.orders"].columns}
    assert ("model.jaffle_shop.stg_orders", "model.jaffle_shop.orders") in snapshot.dependencies


def test_rejects_manifest_without_schema_metadata(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps({"metadata": {"dbt_version": "1.11.13"}}))

    with pytest.raises(ArtifactError, match="manifest schema"):
        load_artifact_snapshot(tmp_path)


def test_rejects_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text("not-json")

    with pytest.raises(ArtifactError, match="Invalid JSON"):
        load_artifact_snapshot(tmp_path)
