# Architecture

## Overview

AI Data Platform Copilot is an evidence-first, tool-augmented RAG application for dbt metadata, lineage, SQL review,
and governed metrics. It follows ports and adapters: FastAPI and Streamlit are delivery adapters; application
services own workflows; immutable Pydantic models define contracts; and SQLite, dbt artifacts, MetricFlow, DuckDB,
and the optional OpenAI Responses API sit behind typed ports.

This is not conventional vector RAG. The current implementation has no embedding model, vector database, arbitrary
text chunking, or nearest-neighbor retrieval. It retrieves structured facts from dbt artifacts, SQLite FTS5, lineage
graphs, MetricFlow, and bounded DuckDB results. The LLM may classify requests and compose prose, but deterministic
services remain authoritative.

MetricFlow provides the governed semantic layer between natural-language requests and warehouse SQL. It defines
metrics, measures, dimensions, entities, joins, and time behavior once, then compiles validated metric requests into
consistent SQL. In an AI application, this prevents the model from inventing formulas or reinterpreting business
definitions, while still allowing users to ask analytical questions conversationally. The resulting SQL and metric
evidence remain inspectable, reproducible, and governed independently of the LLM.

```text
dbt project
   |
   +-- dbt build/docs
   v
manifest.json + catalog.json + semantic_manifest.json
   |
   +-- Metadata parser ----> SQLite + FTS5
   +-- Dependency parser --> NetworkX lineage graph
   +-- Semantic parser ----> Metric and semantic-model definitions
                                  |
User --> Streamlit --> FastAPI --> Chat orchestrator
                                  |
                                  +-- Metadata search
                                  +-- Lineage and impact
                                  +-- Static SQL review
                                  +-- MetricFlow compilation
                                             |
                                    Explicit confirmation
                                             |
                                             v
                                  Read-only DuckDB execution
                                  + deterministic interpretation
                                             |
                                             v
                                  Evidence-backed response
```

## Architectural principles

- Deterministic tools are authoritative; the LLM cannot create factual results or bypass application services.
- Metadata, lineage, and metric answers include stable artifact evidence or explicitly state its absence.
- Confirmed artifact dependencies are distinguished from inferred SQL or expression relationships.
- Infrastructure and provider behavior stays behind typed ports.
- Metric execution accepts structured requests, never client-supplied SQL.
- Missing evidence is represented as a limitation rather than generated content.

## Knowledge ingestion

The knowledge base is generated from the vendored Jaffle Shop dbt project. Its primary inputs are:

- `manifest.json`: models, sources, columns, dependencies, metrics, and semantic models;
- `catalog.json`: physical relations, columns, and data types;
- `semantic_manifest.json`: MetricFlow-compatible semantic definitions;
- dbt model and YAML paths used in evidence references.

The dbt artifact adapter validates artifact schemas, normalizes resources and columns, extracts dependencies from
dbt's `parent_map`, computes checksums, and creates an immutable content-addressed snapshot. A snapshot ID ties each
retrieved resource and dependency to the artifact version from which it came.

Implementation: `src/ai_data_platform_copilot/adapters/dbt/artifacts.py`.

## Metadata retrieval

Normalized metadata is stored in SQLite. The repository contains immutable snapshots, an active-snapshot pointer,
dbt resources, columns, confirmed dependency edges, and an FTS5 index over names, descriptions, columns, file paths,
and tags.

Search is deterministic lexical retrieval rather than embedding similarity. Each result carries an `EvidenceRef`
containing its snapshot ID, dbt unique ID, artifact field, and source path.

Implementation: `src/ai_data_platform_copilot/adapters/sqlite/repository.py`.

## Lineage and impact analysis

Dependencies extracted from dbt artifacts are loaded into a directed NetworkX graph. The application supports
upstream, downstream, and bidirectional traversal with bounded depth, plus downstream impact analysis. Graphs are
cached by immutable snapshot ID.

Edges from dbt's `parent_map` are confirmed. Metric lineage is constructed from the dbt model, semantic model,
measure, metric, and measure-column expression. Simple column expressions are confirmed; complex expressions are
marked inferred.

Implementation: `src/ai_data_platform_copilot/application/services.py` and
`src/ai_data_platform_copilot/application/metric_service.py`.

## Governed semantic retrieval

`ArtifactSemanticProvider` reads governed definitions from the generated dbt manifest. It exposes metrics, labels,
measures, aggregation types, semantic models, compatible dimensions, default metric-time dimensions, primary
entities, and artifact evidence.

The included metrics are `customers`, `orders`, `total_revenue`, and `average_order_value`. Their definitions live in
`demo/jaffle_shop/models/semantic_models.yml`.

Implementation: `src/ai_data_platform_copilot/adapters/dbt/semantic.py`.

## MetricFlow compilation

MetricFlow is the only governed SQL compiler; the LLM does not generate metric SQL. A request such as:

```json
{
  "metric": "total_revenue",
  "group_by": ["payment_method"]
}
```

is validated against artifact-backed definitions and translated into a fixed MetricFlow argument array. Public
dimension names are converted to version-specific identifiers—for example, `payment_method` becomes
`payment__payment_method`.

The adapter passes subprocess arguments without a shell, applies a timeout, normalizes output, parses generated SQL
with SQLGlot, requires one read-only query, and rejects DDL, DML, commands, and multiple statements.

MetricFlow 0.212.0 through `dbt-metricflow` 0.14.0, `dbt-duckdb` 1.10.1, and the included DuckDB project is a verified
compatibility result, not a claim about arbitrary versions or projects.

Implementation: `src/ai_data_platform_copilot/adapters/metricflow/provider.py`.

## Confirmed metric execution

Execution is deliberately narrower than compilation. The UI shows the structured request and compiled SQL and
requires explicit confirmation. After confirmation:

1. The server recompiles the structured request through MetricFlow.
2. Client-supplied SQL is never accepted.
3. Generated SQL is validated again.
4. A spawned child process opens only the included Jaffle Shop DuckDB file.
5. DuckDB uses `read_only=True`, external access is disabled, and resources are bounded.
6. Rows, timings, truncation state, confirmation state, and artifact evidence are returned.

Current boundaries are a five-second timeout, one DuckDB thread, 256 MB memory, a 100-row limit, no free-form
execution filters, and no mutation, DDL, multiple statements, arbitrary SQL, or external database.

The metric service may add deterministic interpretations to executed evidence. For example, it explains a null
`metric_time__year` bucket using returned rows, the governed default time dimension, and its semantic description.

Implementation: `src/ai_data_platform_copilot/adapters/duckdb/metric_executor.py` and
`src/ai_data_platform_copilot/application/metric_service.py`.

## Natural-language orchestration

The optional OpenAI integration has two bounded responsibilities.

### Typed intent classification

The Responses API returns an `IntentDecision` from a closed set of metadata and metric intents. The application then
grounds extracted text against governed definitions. This deterministic stage handles spelling variants and business
aliases, including `AOV`, `total_order_amount` to `total_revenue`, `metric_time_year` to `metric_time__year`, and
payment values such as `credit_card` to grouping by `payment_method`.

An extracted metric or dimension is never trusted merely because it came from typed model output.

### Evidence-backed composition

The selected application service runs before prose is composed. The composer receives the original question,
grounded decision, deterministic evidence, and explicit limitations. Its prompt prohibits inventing metrics,
lineage, SQL, executions, or evidence. When execution is required, chat returns a pending structured query and cannot
confirm it for the user.

Implementation: `src/ai_data_platform_copilot/application/chat_service.py` and
`src/ai_data_platform_copilot/adapters/openai/chat.py`.

## SQL review

SQL review is deterministic static analysis. SQLGlot provides parsing, dialect handling, statement classification,
table and column extraction, and syntax locations. Typed rules produce correctness, safety, maintainability, and
performance findings.

Submitted SQL is never executed. An optional OpenAI explanation provider may restate deterministic findings, but it
may not add, remove, weaken, or contradict them.

Implementation: `src/ai_data_platform_copilot/sql_review/analyzer.py` and
`src/ai_data_platform_copilot/sql_review/rules.py`.

## Application layers

| Layer | Responsibility |
| --- | --- |
| Domain | Immutable Pydantic contracts, evidence, certainty, and structured errors |
| Application | Metadata, lineage, metric, SQL-review, and chat workflows |
| Ports | Typed repository, semantic, execution, chat, and explanation interfaces |
| Adapters | dbt artifacts, SQLite, MetricFlow, DuckDB, and OpenAI implementations |
| Delivery | FastAPI endpoints and Streamlit pages |

This separation keeps providers outside the application core and lets deterministic tests run without an OpenAI key
or paid service.

## API and UI

FastAPI exposes typed endpoints for artifact ingestion, snapshots, metadata, lineage, impact, SQL review, semantic
discovery, metric validation, compilation, confirmed execution, capabilities, and optional chat.

Streamlit provides metadata, lineage, SQL review, governed metric, and Copilot pages. It calls FastAPI through a
shared HTTP client and stores only per-session conversation and pending confirmation state.

Chat is disabled without `OPENAI_API_KEY`. Metadata, lineage, SQL review, metric discovery, compilation, and confirmed
local execution remain available as deterministic capabilities.

## Technology stack

| Area | Technology |
| --- | --- |
| Runtime | Python 3.13.7 |
| Dependency management | `uv` with a committed lock file |
| API | FastAPI and Uvicorn |
| UI | Streamlit |
| Contracts | Pydantic |
| Metadata source | dbt Core artifacts |
| dbt adapter | dbt-duckdb |
| Semantic layer | dbt MetricFlow |
| Analytical database | DuckDB |
| Metadata database and search | SQLite with FTS5 |
| Graph traversal | NetworkX |
| Graph rendering | Graphviz |
| SQL parsing and review | SQLGlot |
| LLM integration | OpenAI Responses API |
| HTTP client | HTTPX |
| Tests | pytest |
| Static analysis | Ruff and strict mypy |
| Packaging | Hatchling |
| Deployment | Docker and Docker Compose |
| CI | GitHub Actions |

Exact versions are pinned in `pyproject.toml` and `uv.lock`.

## Deployment topology

Docker Compose starts `api` on port 8000 and `ui` on port 8501. The UI reaches the API through the Compose network. A
persistent volume stores SQLite metadata. The image builds the vendored dbt project and generates dbt documentation
artifacts during image creation.

Configuration includes `OPENAI_API_KEY`, `OPENAI_MODEL`, `COPILOT_API_URL`, metadata and artifact paths, the dbt
project directory, the MetricFlow executable path, and the demo execution capability flag. See `Dockerfile`,
`compose.yaml`, and `src/ai_data_platform_copilot/settings.py`.

## Testing and evaluation

The repository contains deterministic unit, integration, API, contract, and compatibility tests. External LLM calls
are mocked or disabled. Evaluation cases cover metadata, lineage, SQL review, governed metric discovery, compilation,
execution, lineage, impact, and disabled-chat behavior.

`make check` runs Ruff, strict mypy, and pytest. MetricFlow compatibility has a separate guarded verification path
against only the included project and DuckDB database.

## Current boundaries and future evolution

The current system is structured, evidence-first RAG rather than general-purpose semantic RAG. Its strength is
traceability: factual answers are tied to governed artifacts or bounded execution results.

Current boundaries include no semantic search over large unstructured document collections, no production warehouse
credentials, no arbitrary SQL execution, local semantic-model dimensions aside from supported time grains, no
unattended execution based on an LLM decision, and no dbt MCP provider.

A future hybrid architecture could add embeddings and a vector index for prose documentation. Structured dbt
artifacts, MetricFlow, lineage graphs, and governed execution should remain authoritative for factual metadata and
metric answers.
