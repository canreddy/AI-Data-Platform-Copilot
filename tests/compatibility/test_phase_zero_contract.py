import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "demo" / "jaffle_shop"


def test_vendored_snapshot_records_provenance_and_license() -> None:
    provenance = (PROJECT / "UPSTREAM.md").read_text(encoding="utf-8")
    assert "36bde6cba69d962b83be1d52fc65a0dce1cb4ebb" in provenance
    assert (PROJECT / "LICENSE").is_file()


def test_semantic_definitions_expose_exact_requested_metrics() -> None:
    semantic_config = yaml.safe_load((PROJECT / "models" / "semantic_models.yml").read_text(encoding="utf-8"))
    assert {metric["name"] for metric in semantic_config["metrics"]} == {
        "customers",
        "orders",
        "total_revenue",
        "average_order_value",
    }
    assert {model["name"] for model in semantic_config["semantic_models"]} == {"customers", "orders", "payments"}


def test_generated_artifacts_are_current_and_complete() -> None:
    manifest = json.loads((PROJECT / "target" / "manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((PROJECT / "target" / "catalog.json").read_text(encoding="utf-8"))
    semantic_manifest = json.loads((PROJECT / "target" / "semantic_manifest.json").read_text(encoding="utf-8"))
    assert manifest["metadata"]["dbt_version"] == "1.11.13"
    assert catalog["metadata"]["dbt_version"] == "1.11.13"
    assert semantic_manifest
    assert "model.jaffle_shop.payments" in manifest["nodes"]
