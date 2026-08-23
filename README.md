# AI Data Platform Copilot

An evidence-first portfolio application for exploring dbt metadata and lineage, reviewing SQL, and discovering and
compiling governed metrics. Core capabilities are deterministic and work without an LLM. An optional LLM only
classifies questions and composes answers from typed, evidence-backed tool results.

Phase 0 establishes a reproducible Python, dbt, DuckDB, and MetricFlow compatibility baseline. Phase 1 adds immutable
SQLite/FTS5 metadata snapshots, evidence-backed search, and manifest-confirmed lineage and impact analysis. Phase 2
adds deterministic BigQuery and DuckDB SQL review without execution. Phase 3 adds governed metric discovery,
MetricFlow compilation, metric lineage, the five-page UI, and optional evidence-backed chat. Phase 3.1 adds an
explicitly confirmed, read-only execution path limited to the included DuckDB demo. See
`docs/compatibility.md` and `docs/phase-1.md` through `docs/phase-3.1.md` for details.

## Phase 0 verification

```shell
make sync
make dbt-build
make dbt-docs
make metricflow-check
make check
```

The MetricFlow compatibility command compiles governed SQL and executes only that generated, prevalidated `SELECT`
against the included DuckDB database through a read-only connection and a hard timeout. Phase 3.1 exposes a separate
confirmed metric-request endpoint with equivalent guards; no endpoint accepts SQL text.

## Run the application

```shell
make sync
make dbt-build
make dbt-docs
make run-api
```

Then run `make run-ui` in another terminal and open `http://localhost:8501`. Metadata, lineage, SQL review, and
metrics work without an OpenAI API key. Copilot chat displays a clear disabled state until `OPENAI_API_KEY` is set.
OpenAPI documentation is served at `http://localhost:8000/docs`.

For the local container stack, run `docker compose up --build`. Do not put secrets in the compose file; Compose reads
an optional local `.env`, which is ignored by Git and excluded from the image build.
