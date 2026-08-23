"""Immutable SQLite/FTS5 metadata snapshot repository."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from ai_data_platform_copilot.domain.errors import (
    AmbiguousResourceError,
    ResourceNotFoundError,
    SnapshotNotFoundError,
)
from ai_data_platform_copilot.domain.models import (
    ArtifactSnapshot,
    ColumnMetadata,
    EvidenceRef,
    MetadataResource,
    ResourceType,
    SearchResult,
    SnapshotInfo,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    manifest_checksum TEXT NOT NULL,
    catalog_checksum TEXT,
    dbt_version TEXT NOT NULL,
    generated_at TEXT,
    ingested_at TEXT NOT NULL,
    resource_count INTEGER NOT NULL,
    dependency_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS active_snapshot (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id)
);
CREATE TABLE IF NOT EXISTS resources (
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    unique_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    name TEXT NOT NULL COLLATE NOCASE,
    database_name TEXT,
    schema_name TEXT,
    relation_name TEXT,
    description TEXT NOT NULL,
    file_path TEXT,
    tags_json TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, unique_id)
);
CREATE INDEX IF NOT EXISTS idx_resources_snapshot_name ON resources(snapshot_id, name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_resources_snapshot_type ON resources(snapshot_id, resource_type);
CREATE TABLE IF NOT EXISTS columns (
    snapshot_id TEXT NOT NULL,
    unique_id TEXT NOT NULL,
    name TEXT NOT NULL COLLATE NOCASE,
    description TEXT NOT NULL,
    data_type TEXT,
    ordinal INTEGER,
    PRIMARY KEY (snapshot_id, unique_id, name),
    FOREIGN KEY (snapshot_id, unique_id) REFERENCES resources(snapshot_id, unique_id)
);
CREATE INDEX IF NOT EXISTS idx_columns_snapshot_name ON columns(snapshot_id, name COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS dependencies (
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    parent_id TEXT NOT NULL,
    child_id TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, parent_id, child_id),
    FOREIGN KEY (snapshot_id, parent_id) REFERENCES resources(snapshot_id, unique_id),
    FOREIGN KEY (snapshot_id, child_id) REFERENCES resources(snapshot_id, unique_id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS resources_fts USING fts5(
    snapshot_id UNINDEXED,
    unique_id UNINDEXED,
    name,
    description,
    columns_text,
    file_path,
    tags
);
"""


class SQLiteMetadataRepository:
    """Persist normalized metadata in immutable, content-addressed snapshots."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            try:
                connection.executescript(SCHEMA)
            except sqlite3.OperationalError as error:
                if "fts5" in str(error).lower():
                    raise RuntimeError("This SQLite build does not include required FTS5 support") from error
                raise

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def ingest(self, snapshot: ArtifactSnapshot, *, activate: bool = True) -> tuple[SnapshotInfo, bool]:
        """Insert a new snapshot once and optionally activate it atomically."""
        ingested_at = datetime.now().astimezone()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO snapshots (
                    snapshot_id, manifest_checksum, catalog_checksum, dbt_version, generated_at, ingested_at,
                    resource_count, dependency_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.manifest_checksum,
                    snapshot.catalog_checksum,
                    snapshot.dbt_version,
                    snapshot.generated_at.isoformat() if snapshot.generated_at else None,
                    ingested_at.isoformat(),
                    len(snapshot.resources),
                    len(snapshot.dependencies),
                ),
            )
            created = cursor.rowcount == 1
            if created:
                for resource in snapshot.resources:
                    connection.execute(
                        """
                        INSERT INTO resources (
                            snapshot_id, unique_id, resource_type, name, database_name, schema_name, relation_name,
                            description, file_path, tags_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            snapshot.snapshot_id,
                            resource.unique_id,
                            resource.resource_type.value,
                            resource.name,
                            resource.database,
                            resource.schema_name,
                            resource.relation_name,
                            resource.description,
                            resource.file_path,
                            json.dumps(resource.tags),
                        ),
                    )
                    for column in resource.columns:
                        connection.execute(
                            """
                            INSERT INTO columns (
                                snapshot_id, unique_id, name, description, data_type, ordinal
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                snapshot.snapshot_id,
                                resource.unique_id,
                                column.name,
                                column.description,
                                column.data_type,
                                column.index,
                            ),
                        )
                    columns_text = " ".join(
                        f"{column.name} {column.description} {column.data_type or ''}" for column in resource.columns
                    )
                    connection.execute(
                        """
                        INSERT INTO resources_fts (
                            snapshot_id, unique_id, name, description, columns_text, file_path, tags
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            snapshot.snapshot_id,
                            resource.unique_id,
                            resource.name,
                            resource.description,
                            columns_text,
                            resource.file_path or "",
                            " ".join(resource.tags),
                        ),
                    )
                connection.executemany(
                    "INSERT INTO dependencies (snapshot_id, parent_id, child_id) VALUES (?, ?, ?)",
                    ((snapshot.snapshot_id, parent, child) for parent, child in snapshot.dependencies),
                )
            if activate:
                connection.execute(
                    """
                    INSERT INTO active_snapshot (singleton, snapshot_id) VALUES (1, ?)
                    ON CONFLICT(singleton) DO UPDATE SET snapshot_id = excluded.snapshot_id
                    """,
                    (snapshot.snapshot_id,),
                )
        return self.get_snapshot(snapshot.snapshot_id), created

    def active_snapshot(self) -> SnapshotInfo:
        return self.get_snapshot()

    def get_snapshot(self, snapshot_id: str | None = None) -> SnapshotInfo:
        with self._connect() as connection:
            active_row = connection.execute("SELECT snapshot_id FROM active_snapshot WHERE singleton = 1").fetchone()
            selected_id = snapshot_id or (str(active_row["snapshot_id"]) if active_row else None)
            if selected_id is None:
                raise SnapshotNotFoundError("No active metadata snapshot exists; ingest dbt artifacts first")
            row = connection.execute("SELECT * FROM snapshots WHERE snapshot_id = ?", (selected_id,)).fetchone()
            if row is None:
                raise SnapshotNotFoundError(f"Metadata snapshot not found: {selected_id}")
            return self._snapshot_from_row(row, active_id=str(active_row["snapshot_id"]) if active_row else None)

    @staticmethod
    def _snapshot_from_row(row: sqlite3.Row, *, active_id: str | None) -> SnapshotInfo:
        return SnapshotInfo(
            snapshot_id=str(row["snapshot_id"]),
            manifest_checksum=str(row["manifest_checksum"]),
            catalog_checksum=str(row["catalog_checksum"]) if row["catalog_checksum"] else None,
            dbt_version=str(row["dbt_version"]),
            generated_at=datetime.fromisoformat(str(row["generated_at"])) if row["generated_at"] else None,
            ingested_at=datetime.fromisoformat(str(row["ingested_at"])),
            resource_count=int(row["resource_count"]),
            dependency_count=int(row["dependency_count"]),
            active=str(row["snapshot_id"]) == active_id,
        )

    def search(
        self,
        query: str,
        *,
        resource_types: Iterable[ResourceType] = (),
        limit: int = 20,
        snapshot_id: str | None = None,
    ) -> tuple[SearchResult, ...]:
        selected_id = self.get_snapshot(snapshot_id).snapshot_id
        normalized_query = query.strip().casefold()
        if not normalized_query:
            return ()
        selected_types = tuple(resource_type.value for resource_type in resource_types)
        with self._connect() as connection:
            sql = "SELECT * FROM resources WHERE snapshot_id = ?"
            parameters: list[object] = [selected_id]
            if selected_types:
                placeholders = ", ".join("?" for _ in selected_types)
                sql += f" AND resource_type IN ({placeholders})"
                parameters.extend(selected_types)
            resource_rows = connection.execute(sql, parameters).fetchall()
            tokens = re.findall(r"[\w]+", normalized_query, flags=re.UNICODE)
            fts_ids: set[str] = set()
            if tokens:
                fts_query = " OR ".join(f'"{token}"*' for token in tokens)
                fts_rows = connection.execute(
                    "SELECT unique_id FROM resources_fts WHERE snapshot_id = ? AND resources_fts MATCH ?",
                    (selected_id, fts_query),
                ).fetchall()
                fts_ids = {str(row["unique_id"]) for row in fts_rows}

            results: list[SearchResult] = []
            for row in resource_rows:
                resource = self._resource_from_row(connection, row)
                exact_columns = tuple(
                    column.name for column in resource.columns if column.name.casefold() == normalized_query
                )
                searchable = " ".join(
                    (
                        resource.name,
                        resource.description,
                        resource.file_path or "",
                        " ".join(resource.tags),
                        " ".join(f"{column.name} {column.description}" for column in resource.columns),
                    )
                ).casefold()
                if resource.name.casefold() == normalized_query:
                    score, reason = 1.0, "exact_name"
                elif exact_columns:
                    score, reason = 0.95, "exact_column"
                elif normalized_query in resource.name.casefold():
                    score, reason = 0.85, "name_contains"
                elif normalized_query in searchable:
                    score, reason = 0.75, "keyword"
                elif resource.unique_id in fts_ids:
                    score, reason = 0.65, "full_text"
                else:
                    continue
                results.append(
                    SearchResult(
                        resource=resource,
                        score=score,
                        match_reason=reason,
                        matched_columns=exact_columns,
                    )
                )
        results.sort(key=lambda result: (-result.score, result.resource.name, result.resource.unique_id))
        return tuple(results[:limit])

    def get_resource(self, selector: str, *, snapshot_id: str | None = None) -> MetadataResource:
        selected_id = self.get_snapshot(snapshot_id).snapshot_id
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM resources
                WHERE snapshot_id = ? AND (unique_id = ? OR name = ? COLLATE NOCASE)
                ORDER BY CASE WHEN unique_id = ? THEN 0 ELSE 1 END, unique_id
                """,
                (selected_id, selector, selector, selector),
            ).fetchall()
            if not rows:
                raise ResourceNotFoundError(f"dbt resource not found: {selector}")
            exact_unique_id = [row for row in rows if str(row["unique_id"]) == selector]
            if exact_unique_id:
                return self._resource_from_row(connection, exact_unique_id[0])
            if len(rows) > 1:
                matches = ", ".join(str(row["unique_id"]) for row in rows)
                raise AmbiguousResourceError(f"Resource name {selector!r} is ambiguous: {matches}")
            return self._resource_from_row(connection, rows[0])

    def list_resources(self, *, snapshot_id: str | None = None) -> tuple[MetadataResource, ...]:
        selected_id = self.get_snapshot(snapshot_id).snapshot_id
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM resources WHERE snapshot_id = ? ORDER BY unique_id", (selected_id,)
            ).fetchall()
            return tuple(self._resource_from_row(connection, row) for row in rows)

    def list_dependencies(self, *, snapshot_id: str | None = None) -> tuple[tuple[str, str], ...]:
        selected_id = self.get_snapshot(snapshot_id).snapshot_id
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT parent_id, child_id FROM dependencies WHERE snapshot_id = ? ORDER BY parent_id, child_id",
                (selected_id,),
            ).fetchall()
            return tuple((str(row["parent_id"]), str(row["child_id"])) for row in rows)

    @staticmethod
    def _resource_from_row(connection: sqlite3.Connection, row: sqlite3.Row) -> MetadataResource:
        snapshot_id = str(row["snapshot_id"])
        unique_id = str(row["unique_id"])
        column_rows = connection.execute(
            """
            SELECT * FROM columns WHERE snapshot_id = ? AND unique_id = ?
            ORDER BY ordinal IS NULL, ordinal, name
            """,
            (snapshot_id, unique_id),
        ).fetchall()
        file_path = str(row["file_path"]) if row["file_path"] else None
        return MetadataResource(
            snapshot_id=snapshot_id,
            unique_id=unique_id,
            resource_type=ResourceType(str(row["resource_type"])),
            name=str(row["name"]),
            database=str(row["database_name"]) if row["database_name"] else None,
            schema_name=str(row["schema_name"]) if row["schema_name"] else None,
            relation_name=str(row["relation_name"]) if row["relation_name"] else None,
            description=str(row["description"]),
            file_path=file_path,
            tags=tuple(json.loads(str(row["tags_json"]))),
            columns=tuple(
                ColumnMetadata(
                    name=str(column["name"]),
                    description=str(column["description"]),
                    data_type=str(column["data_type"]) if column["data_type"] else None,
                    index=int(column["ordinal"]) if column["ordinal"] is not None else None,
                )
                for column in column_rows
            ),
            evidence=(
                EvidenceRef(
                    snapshot_id=snapshot_id,
                    unique_id=unique_id,
                    field=f"{('sources' if row['resource_type'] == 'source' else 'nodes')}.{unique_id}",
                    file_path=file_path,
                ),
            ),
        )
