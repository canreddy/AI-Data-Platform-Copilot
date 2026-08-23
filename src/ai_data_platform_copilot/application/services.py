"""Deterministic metadata and lineage use cases."""

from __future__ import annotations

import time
from collections.abc import Iterable

import networkx as nx

from ai_data_platform_copilot.domain.models import (
    Certainty,
    EvidenceRef,
    ImpactResponse,
    LineageEdge,
    LineageNode,
    LineageResponse,
    MetadataResource,
    ResourceType,
    SearchResponse,
)
from ai_data_platform_copilot.ports.metadata_repository import MetadataRepository


class MetadataService:
    """Metadata search and detail operations."""

    def __init__(self, repository: MetadataRepository) -> None:
        self._repository = repository

    def search(
        self,
        query: str,
        *,
        resource_types: Iterable[ResourceType] = (),
        limit: int = 20,
        snapshot_id: str | None = None,
    ) -> SearchResponse:
        started = time.perf_counter()
        snapshot = self._repository.get_snapshot(snapshot_id)
        results = self._repository.search(
            query,
            resource_types=resource_types,
            limit=limit,
            snapshot_id=snapshot.snapshot_id,
        )
        return SearchResponse(
            query=query,
            snapshot_id=snapshot.snapshot_id,
            results=results,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    def details(self, selector: str, *, snapshot_id: str | None = None) -> MetadataResource:
        return self._repository.get_resource(selector, snapshot_id=snapshot_id)


class LineageService:
    """Confirmed manifest-based dependency traversal."""

    def __init__(self, repository: MetadataRepository) -> None:
        self._repository = repository
        self._graphs: dict[str, nx.DiGraph[str]] = {}

    def lineage(
        self,
        selector: str,
        *,
        direction: str = "both",
        max_depth: int = 5,
        snapshot_id: str | None = None,
    ) -> LineageResponse:
        if direction not in {"upstream", "downstream", "both"}:
            raise ValueError("direction must be upstream, downstream, or both")
        started = time.perf_counter()
        snapshot = self._repository.get_snapshot(snapshot_id)
        root = self._repository.get_resource(selector, snapshot_id=snapshot.snapshot_id)
        resources = {
            resource.unique_id: resource
            for resource in self._repository.list_resources(snapshot_id=snapshot.snapshot_id)
        }
        graph = self._graph(snapshot.snapshot_id, resources)
        depths = self._depths(graph, root.unique_id, direction=direction, cutoff=max_depth)
        included = set(depths)
        nodes = tuple(
            self._node(resources[unique_id], depth)
            for unique_id, depth in sorted(depths.items(), key=lambda item: (item[1], resources[item[0]].name, item[0]))
        )
        edges = tuple(
            LineageEdge(
                source=parent,
                target=child,
                certainty=Certainty.CONFIRMED,
                evidence=EvidenceRef(
                    snapshot_id=snapshot.snapshot_id,
                    unique_id=child,
                    field=f"parent_map.{child}",
                    file_path=resources[child].file_path,
                ),
            )
            for parent, child in sorted(graph.edges())
            if parent in included and child in included
        )
        return LineageResponse(
            snapshot_id=snapshot.snapshot_id,
            root=root,
            direction=direction,
            max_depth=max_depth,
            nodes=nodes,
            edges=edges,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    def impact(
        self,
        selector: str,
        *,
        max_depth: int = 10,
        snapshot_id: str | None = None,
    ) -> ImpactResponse:
        result = self.lineage(
            selector,
            direction="downstream",
            max_depth=max_depth,
            snapshot_id=snapshot_id,
        )
        return ImpactResponse(**result.model_dump(), affected_count=max(len(result.nodes) - 1, 0))

    def _graph(self, snapshot_id: str, resources: dict[str, MetadataResource]) -> nx.DiGraph[str]:
        cached = self._graphs.get(snapshot_id)
        if cached is not None:
            return cached
        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_nodes_from(resources)
        graph.add_edges_from(self._repository.list_dependencies(snapshot_id=snapshot_id))
        self._graphs[snapshot_id] = graph
        return graph

    @staticmethod
    def _depths(graph: nx.DiGraph[str], root: str, *, direction: str, cutoff: int) -> dict[str, int]:
        downstream = dict(nx.single_source_shortest_path_length(graph, root, cutoff=cutoff))
        upstream = dict(nx.single_source_shortest_path_length(graph.reverse(copy=False), root, cutoff=cutoff))
        if direction == "downstream":
            return downstream
        if direction == "upstream":
            return upstream
        return {
            unique_id: min(depth for depth in (downstream.get(unique_id), upstream.get(unique_id)) if depth is not None)
            for unique_id in downstream.keys() | upstream.keys()
        }

    @staticmethod
    def _node(resource: MetadataResource, depth: int) -> LineageNode:
        return LineageNode(
            unique_id=resource.unique_id,
            name=resource.name,
            resource_type=resource.resource_type,
            depth=depth,
            evidence=resource.evidence[0],
        )
