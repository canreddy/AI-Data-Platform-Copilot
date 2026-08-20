# AI Data Platform Copilot

An evidence-first portfolio application for exploring dbt metadata and lineage, reviewing SQL, and discovering and
compiling governed metrics. Core capabilities are deterministic and work without an LLM. An optional LLM only
classifies questions and composes answers from typed, evidence-backed tool results.

Phase 0 establishes a reproducible Python, dbt, DuckDB, and MetricFlow compatibility baseline. See
`docs/compatibility.md` for the verified version matrix and commands.

## Phase 0 verification

```shell
make sync
make dbt-build
make dbt-docs
make metricflow-check
make check
```

The MetricFlow compatibility command is development-only. It compiles governed SQL and executes only that generated,
prevalidated `SELECT` against the included DuckDB database through a read-only connection and a hard timeout. No
application endpoint exposes execution.

