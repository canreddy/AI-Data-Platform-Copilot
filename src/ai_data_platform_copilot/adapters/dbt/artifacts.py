"""Strict-enough dbt manifest and catalog normalization for Phase 1."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_data_platform_copilot.domain.errors import ArtifactError
from ai_data_platform_copilot.domain.models import (
    ArtifactSnapshot,
    ColumnMetadata,
    EvidenceRef,
    MetadataResource,
    ResourceType,
)

SUPPORTED_RESOURCE_TYPES = {resource_type.value: resource_type for resource_type in ResourceType}


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], bytes] | tuple[None, None]:
    if not path.is_file():
        if required:
            raise ArtifactError(f"Required dbt artifact does not exist: {path}")
        return None, None
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ArtifactError(f"Invalid JSON in dbt artifact {path}: {error}") from error
    if not isinstance(value, dict):
        raise ArtifactError(f"dbt artifact must contain a JSON object: {path}")
    return value, raw


def _checksum(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str))


def _columns(
    manifest_node: dict[str, Any],
    catalog_node: dict[str, Any],
) -> tuple[ColumnMetadata, ...]:
    manifest_columns = manifest_node.get("columns")
    catalog_columns = catalog_node.get("columns")
    manifest_columns = manifest_columns if isinstance(manifest_columns, dict) else {}
    catalog_columns = catalog_columns if isinstance(catalog_columns, dict) else {}
    names = list(dict.fromkeys([*manifest_columns.keys(), *catalog_columns.keys()]))
    normalized: list[ColumnMetadata] = []
    for name in names:
        manifest_column = manifest_columns.get(name, {})
        catalog_column = catalog_columns.get(name, {})
        manifest_column = manifest_column if isinstance(manifest_column, dict) else {}
        catalog_column = catalog_column if isinstance(catalog_column, dict) else {}
        index = catalog_column.get("index")
        normalized.append(
            ColumnMetadata(
                name=str(name),
                description=str(manifest_column.get("description") or catalog_column.get("comment") or ""),
                data_type=_optional_string(catalog_column.get("type"))
                or _optional_string(manifest_column.get("data_type")),
                index=index if isinstance(index, int) else None,
            )
        )
    return tuple(sorted(normalized, key=lambda column: (column.index is None, column.index or 0, column.name)))


def _artifact_sections(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    for section_name in ("nodes", "sources"):
        section = artifact.get(section_name)
        if isinstance(section, dict):
            combined.update({str(key): value for key, value in section.items() if isinstance(value, dict)})
    return combined


def load_artifact_snapshot(artifact_dir: Path) -> ArtifactSnapshot:
    """Load and normalize one content-addressed dbt artifact snapshot."""
    manifest_path = artifact_dir / "manifest.json"
    catalog_path = artifact_dir / "catalog.json"
    manifest, manifest_raw = _load_json(manifest_path, required=True)
    catalog, catalog_raw = _load_json(catalog_path, required=False)
    assert manifest is not None and manifest_raw is not None

    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        raise ArtifactError("manifest.json is missing its metadata object")
    dbt_version = _optional_string(metadata.get("dbt_version"))
    if dbt_version is None:
        raise ArtifactError("manifest.json is missing metadata.dbt_version")
    schema_url = _optional_string(metadata.get("dbt_schema_version"))
    if schema_url is None or "/manifest/" not in schema_url:
        raise ArtifactError(f"Unsupported or missing manifest schema: {schema_url!r}")

    catalog = catalog or {}
    manifest_nodes = _artifact_sections(manifest)
    catalog_nodes = _artifact_sections(catalog)
    manifest_checksum = _checksum(manifest_raw)
    catalog_checksum = _checksum(catalog_raw) if catalog_raw is not None else None
    snapshot_hasher = hashlib.sha256()
    snapshot_hasher.update(manifest_raw)
    snapshot_hasher.update(b"\0")
    snapshot_hasher.update(catalog_raw or b"")
    snapshot_id = snapshot_hasher.hexdigest()

    resources: list[MetadataResource] = []
    for unique_id, node in manifest_nodes.items():
        resource_name = node.get("resource_type")
        if resource_name not in SUPPORTED_RESOURCE_TYPES:
            continue
        catalog_node = catalog_nodes.get(unique_id, {})
        original_file_path = _optional_string(node.get("original_file_path"))
        resources.append(
            MetadataResource(
                snapshot_id=snapshot_id,
                unique_id=unique_id,
                resource_type=SUPPORTED_RESOURCE_TYPES[str(resource_name)],
                name=str(node.get("name") or unique_id),
                database=_optional_string(node.get("database")),
                schema_name=_optional_string(node.get("schema")),
                relation_name=_optional_string(node.get("relation_name")),
                description=str(node.get("description") or ""),
                file_path=original_file_path,
                tags=_string_list(node.get("tags")),
                columns=_columns(node, catalog_node),
                evidence=(
                    EvidenceRef(
                        snapshot_id=snapshot_id,
                        unique_id=unique_id,
                        field=f"{('sources' if resource_name == 'source' else 'nodes')}.{unique_id}",
                        file_path=original_file_path,
                    ),
                ),
            )
        )

    resource_ids = {resource.unique_id for resource in resources}
    parent_map = manifest.get("parent_map")
    parent_map = parent_map if isinstance(parent_map, dict) else {}
    dependencies: set[tuple[str, str]] = set()
    for child_id, parent_ids in parent_map.items():
        if child_id not in resource_ids or not isinstance(parent_ids, list):
            continue
        dependencies.update(
            (parent_id, str(child_id))
            for parent_id in parent_ids
            if isinstance(parent_id, str) and parent_id in resource_ids
        )

    generated_at: datetime | None = None
    generated_at_raw = _optional_string(metadata.get("generated_at"))
    if generated_at_raw is not None:
        try:
            generated_at = datetime.fromisoformat(generated_at_raw.replace("Z", "+00:00"))
        except ValueError as error:
            raise ArtifactError(f"Invalid manifest generated_at timestamp: {generated_at_raw}") from error

    return ArtifactSnapshot(
        snapshot_id=snapshot_id,
        manifest_checksum=manifest_checksum,
        catalog_checksum=catalog_checksum,
        dbt_version=dbt_version,
        generated_at=generated_at,
        resources=tuple(sorted(resources, key=lambda resource: resource.unique_id)),
        dependencies=tuple(sorted(dependencies)),
    )
