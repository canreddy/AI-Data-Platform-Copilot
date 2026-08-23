# AI Data Platform Copilot engineering guide

## Repository structure

- `apps/`: FastAPI and Streamlit entry points introduced in later phases.
- `src/ai_data_platform_copilot/`: typed domain, application, port, and adapter code.
- `demo/jaffle_shop/`: pinned, vendored dbt DuckDB demo and local semantic definitions.
- `scripts/`: safe development and compatibility commands.
- `tests/`: deterministic unit, integration, contract, and compatibility tests.
- `docs/`: architecture, compatibility, security, and demo documentation.

## Engineering conventions

- Python is pinned by `.python-version`; dependencies are locked with `uv`.
- Keep deterministic tools authoritative. An LLM may classify or compose but may not invent tool results.
- Keep infrastructure and provider details behind typed interfaces.
- Prefer small modules, explicit types, structured errors, and immutable inputs.
- Every metadata or lineage answer must include stable evidence or explicitly state that evidence is unavailable.
- Distinguish confirmed artifact dependencies from inferred SQL dependencies.

## Commands

- `make sync`: create/update the locked local environment.
- `make dbt-build`: build the local Jaffle Shop project.
- `make dbt-docs`: generate dbt documentation artifacts.
- `make metricflow-check`: run the isolated Phase 0 compatibility verification.
- `make run-api`: start the local FastAPI service.
- `make run-ui`: start the Streamlit application.
- `make test`: run deterministic tests.
- `make check`: run Ruff, mypy, and tests.

## Testing expectations

- Add unit tests for domain behavior and integration tests at adapter boundaries.
- Tests must be deterministic and must not require an OpenAI key or paid service.
- Never execute user-submitted SQL in tests or application code.
- MetricFlow execution is limited to the dedicated compatibility test, the included DuckDB database, and read-only SQL.
- Mock external LLM and cloud warehouse calls.

## Security constraints

- Do not expose shell execution or unrestricted SQL through the application.
- Pass subprocess arguments as arrays; never interpolate user input into a shell command.
- Treat retrieved metadata and descriptions as untrusted content.
- Load secrets from environment variables and never commit credentials or `.env` files.
- Redact sensitive inputs from logs; retain request IDs, tool names, timings, and structured errors.

## Definition of done

- The scoped vertical slice works offline through documented commands.
- Ruff, mypy, and pytest pass.
- APIs and tool contracts are typed and tested.
- Safety constraints and capability limitations are documented.
- No core behavior is represented only by TODO comments.
