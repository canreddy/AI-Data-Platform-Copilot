# Deployment notes

`compose.yaml` is a local demonstration deployment, not production infrastructure. It builds dbt artifacts into the
image, starts FastAPI and Streamlit separately, persists only the SQLite index, and never mounts the host `.env`.

A production deployment should add authentication and authorization, TLS, a managed metadata store, secret-manager
integration, network policy, rate limiting, observability export, artifact promotion rather than runtime builds, and
an explicit compatibility certification for its dbt/MetricFlow/warehouse versions. dbt MCP can be introduced later
behind the semantic provider port without changing application contracts.

The Phase 3.1 executor is demo-only and must not be pointed at a production warehouse. A production executor requires
separate authorization, cost controls, query policies, audit retention, and warehouse-specific certification.
