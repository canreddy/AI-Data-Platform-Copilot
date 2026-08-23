# Phase 3.1: confirmed demo metric execution

Phase 3.1 adds one deliberately narrow execution path so the local portfolio demo can return governed metric values.
It does not add arbitrary SQL execution or a general warehouse query API.

## Execution contract

`POST /api/v1/metric-queries/execute` accepts only a structured `MetricQueryRequest` plus literal
`confirmed: true`. The server recompiles the request through MetricFlow; clients cannot supply SQL. The resulting SQL
must parse as exactly one read-only query and must not contain DDL or DML.

Execution is isolated in a spawned child process with:

- the fixed `demo/jaffle_shop/jaffle_shop.duckdb` database;
- a DuckDB `read_only=True` connection;
- a five-second hard parent timeout;
- one DuckDB thread and a 256 MB memory limit;
- a 100-row response limit;
- structured database, timing, confirmation, truncation, and artifact evidence.

The Metrics explorer shows compiled SQL before execution and requires a confirmation checkbox. Copilot returns a
pending execution request first; its confirmation control invokes the deterministic endpoint and adds the confirmed
result to chat history. The LLM never receives execution authority.

## Verified example

The governed `total_revenue` request constrained to 2018 compiles with MetricFlow and returns `1672.0` from the
included read-only demo database. This value is demo evidence, not a claim about an external warehouse.

## Non-goals

- user-submitted SQL execution;
- mutation, DDL, multi-statement, or unrestricted query endpoints;
- databases other than the included Jaffle Shop DuckDB file;
- unattended execution from an LLM decision;
- production warehouse credentials or production execution.
