"""Metadata persistence boundary."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from ai_data_platform_copilot.domain.models import (
    ArtifactSnapshot,
    MetadataResource,
    ResourceType,
    SearchResult,
    SnapshotInfo,
)


class MetadataRepository(Protocol):
    """Store and retrieve immutable artifact snapshots."""

    def ingest(self, snapshot: ArtifactSnapshot, *, activate: bool = True) -> tuple[SnapshotInfo, bool]: ...

    def active_snapshot(self) -> SnapshotInfo: ...

    def get_snapshot(self, snapshot_id: str | None = None) -> SnapshotInfo: ...

    def search(
        self,
        query: str,
        *,
        resource_types: Iterable[ResourceType] = (),
        limit: int = 20,
        snapshot_id: str | None = None,
    ) -> tuple[SearchResult, ...]: ...

    def get_resource(self, selector: str, *, snapshot_id: str | None = None) -> MetadataResource: ...

    def list_resources(self, *, snapshot_id: str | None = None) -> tuple[MetadataResource, ...]: ...

    def list_dependencies(self, *, snapshot_id: str | None = None) -> tuple[tuple[str, str], ...]: ...
