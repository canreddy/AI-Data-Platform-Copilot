# Phase 1: metadata and lineage vertical slice

## Outcome

Phase 1 provides offline, deterministic dbt metadata search and manifest-confirmed lineage. No LLM, cloud service,
warehouse query execution, or vector search is involved.

## Artifact ingestion

`manifest.json` is required and `catalog.json` is optional. The parser validates core metadata, normalizes models,
sources, seeds, snapshots, columns, descriptions, tags, relations, file paths, and dependencies, and computes a SHA-256
snapshot ID from the exact artifact bytes.

Snapshots are immutable: resources, columns, FTS rows, and dependency edges are inserted only when a new content hash
is observed. Reingesting identical artifacts is idempotent. Activation is a separate one-row pointer, allowing a new
snapshot to become current without mutating an older snapshot.

## Search behavior

SQLite FTS5 is mandatory and initialized with the repository schema. Search ranking is deterministic:

1. exact resource name;
2. exact column name;
3. resource-name substring;
4. case-insensitive keyword match;
5. FTS5 token-prefix match.

Results can be filtered by dbt resource type. Every resource includes its snapshot ID, dbt unique ID, manifest field,
and original project file as stable evidence.

## Lineage behavior

The directed graph uses only dbt `parent_map` relationships that connect indexed resources. Edges retain their native
upstream-to-downstream orientation. Upstream, downstream, bidirectional, depth-limited, and impact traversals are
cycle-safe through NetworkX shortest-path traversal.

All Phase 1 edges are labelled `confirmed`. SQL-derived column lineage is intentionally deferred and must later be
labelled `inferred`.

## API

- `POST /api/v1/artifacts/ingest`
- `GET /api/v1/artifacts/active`
- `GET /api/v1/metadata/search`
- `GET /api/v1/models/{selector}`
- `GET /api/v1/lineage/{selector}`
- `GET /api/v1/impact/{selector}`
- `GET /health/live`
- `GET /health/ready`

The ingestion endpoint accepts no filesystem path. It can read only the artifact directory configured by the process
owner through `COPILOT_ARTIFACT_DIR`.

## Local demonstration

```shell
make sync
make dbt-build
make dbt-docs
make run-api
```

In another terminal:

```shell
make run-ui
```

Open `http://localhost:8501`. API documentation is available at `http://localhost:8000/docs`.

Demonstrated questions:

- What does the `orders` model contain?
- Which models contain `customer_id`?
- What is upstream of `customers`?
- What depends on `stg_orders`?

## Limitations

- Lineage is model/resource-level only.
- Search has no embeddings or semantic reranking.
- Snapshots are local to one SQLite database and one API process.
- The Streamlit pages require the local FastAPI process to be running.
- Metric-aware lineage remains Phase 3 scope.

