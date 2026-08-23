# Security boundaries

- Submitted SQL is parsed for review and never executed.
- MetricFlow is invoked through a fixed executable with argument arrays and a timeout; compiled SQL is validated as a
  single read-only query.
- Phase 3.1 may execute only a freshly server-compiled, explicitly confirmed metric query against the included
  DuckDB file. It uses a read-only connection, isolated child process, timeout, memory/thread constraints, and row cap.
- No API accepts SQL text, and SQL review remains non-executing.
- Metadata descriptions and tool results are treated as untrusted content in OpenAI prompts.
- Optional chat can select only a closed set of application tools. It can prepare a structured metric request but
  cannot execute it; the user must confirm through the deterministic execution endpoint.
- Secrets are environment-backed. `.env` is ignored and is excluded from container build context.
- Request logs include IDs, route, status, duration, and do not include SQL, questions, filters, or API keys.
