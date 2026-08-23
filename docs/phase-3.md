# Phase 3: governed metrics and optional Copilot

Phase 3 adds artifact-backed semantic discovery, guarded MetricFlow SQL compilation, metric-aware lineage and impact,
a Metrics explorer, optional evidence-backed chat, deterministic evaluation cases, local containers, and CI.

## Provider boundary

`ArtifactSemanticProvider` reads `manifest.json` and remains authoritative for metric definitions, semantic models,
measures, dimensions, source files, and evidence. `MetricFlowProvider` delegates discovery to that provider and invokes
only the configured `mf query ... --explain --quiet` command for compilation. Arguments are passed as an array, the
process has a timeout, and returned SQL must parse as exactly one read-only query. Phase 3 itself is compile-only;
the separately approved Phase 3.1 path may execute only confirmed governed queries on the included read-only demo.

MetricFlow 0.212.0 with dbt-metricflow 0.14.0 and dbt-duckdb 1.10.1 was verified against the included DuckDB project.
This remains a pinned compatibility result, not a claim about arbitrary versions or DuckDB projects.

## API

- `GET /api/v1/metrics`, `/metrics/{name}`, and `/metrics/{name}/dimensions`
- `GET /api/v1/semantic-models` and `/semantic-models/{name}`
- `POST /api/v1/metric-queries/validate`, `/metric-queries/compile`, and confirmed `/metric-queries/execute`
- `GET /api/v1/metrics/{name}/lineage` and `/metrics/impact/{model}`
- `GET /api/v1/capabilities` and optional `POST /api/v1/chat`

The chat endpoint is disabled without `OPENAI_API_KEY`. When enabled, typed model output selects from a closed intent
set; the application invokes a mapped deterministic service and gives only its evidence to the prose composer.

## Run

```bash
make dbt-build dbt-docs
make run-api
make run-ui
```

Or run `docker compose up --build`. The UI is at port 8501 and the API at port 8000.

## Known limits

- Discovery exposes dimensions local to the metric's semantic model plus standard `metric_time` grains. Joined
  dimensions across entity paths are left to a future broader MetricFlow integration.
- MetricFlow time bounds are supported. Free-form filters compile but are not exposed by the execution UI.
- Column-to-model metric lineage is confirmed only for a simple measure expression. Complex expressions are marked
  inferred.
- dbt MCP is a documented future provider option; it is not used in this phase.
