"""Typed metadata, evidence, and lineage contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ResourceType(StrEnum):
    """dbt resource types supported by the first metadata index."""

    MODEL = "model"
    SEED = "seed"
    SNAPSHOT = "snapshot"
    SOURCE = "source"


class Certainty(StrEnum):
    """How strongly an edge is supported by available evidence."""

    CONFIRMED = "confirmed"
    INFERRED = "inferred"


class EvidenceRef(BaseModel):
    """Stable pointer back to a dbt artifact or project file."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    unique_id: str
    artifact: str = "manifest.json"
    field: str
    file_path: str | None = None


class ColumnMetadata(BaseModel):
    """Normalized column metadata from manifest and catalog artifacts."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str = ""
    data_type: str | None = None
    index: int | None = None


class MetadataResource(BaseModel):
    """Normalized searchable dbt resource."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    unique_id: str
    resource_type: ResourceType
    name: str
    database: str | None = None
    schema_name: str | None = None
    relation_name: str | None = None
    description: str = ""
    file_path: str | None = None
    tags: tuple[str, ...] = ()
    columns: tuple[ColumnMetadata, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()


class SnapshotInfo(BaseModel):
    """Content-addressed artifact snapshot metadata."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    manifest_checksum: str
    catalog_checksum: str | None = None
    dbt_version: str
    generated_at: datetime | None = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resource_count: int
    dependency_count: int
    active: bool = False


class ArtifactSnapshot(BaseModel):
    """Fully normalized immutable artifact snapshot ready for persistence."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    manifest_checksum: str
    catalog_checksum: str | None = None
    dbt_version: str
    generated_at: datetime | None = None
    resources: tuple[MetadataResource, ...]
    dependencies: tuple[tuple[str, str], ...]


class SearchResult(BaseModel):
    """Ranked resource result with match context and evidence."""

    model_config = ConfigDict(frozen=True)

    resource: MetadataResource
    score: float
    match_reason: str
    matched_columns: tuple[str, ...] = ()


class SearchResponse(BaseModel):
    """Metadata search response."""

    model_config = ConfigDict(frozen=True)

    query: str
    snapshot_id: str
    results: tuple[SearchResult, ...]
    duration_ms: float


class LineageNode(BaseModel):
    """Resource represented in a lineage traversal."""

    model_config = ConfigDict(frozen=True)

    unique_id: str
    name: str
    resource_type: ResourceType
    depth: int
    evidence: EvidenceRef


class LineageEdge(BaseModel):
    """Directed dependency edge from upstream parent to downstream child."""

    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    certainty: Certainty = Certainty.CONFIRMED
    evidence: EvidenceRef


class LineageResponse(BaseModel):
    """Lineage or impact traversal result."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    root: MetadataResource
    direction: str
    max_depth: int
    nodes: tuple[LineageNode, ...]
    edges: tuple[LineageEdge, ...]
    duration_ms: float


class ImpactResponse(LineageResponse):
    """Downstream impact result with an affected-resource count."""

    affected_count: int


class IngestResponse(BaseModel):
    """Artifact ingestion response."""

    model_config = ConfigDict(frozen=True)

    snapshot: SnapshotInfo
    created: bool
    duration_ms: float
