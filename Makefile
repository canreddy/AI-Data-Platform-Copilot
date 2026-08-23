.PHONY: sync dbt-build dbt-docs metricflow-check run-api run-ui test lint typecheck check

export UV_CACHE_DIR := .uv-cache

sync:
	uv sync --frozen

dbt-build:
	cd demo/jaffle_shop && ../../.venv/bin/dbt build --profiles-dir .

dbt-docs:
	cd demo/jaffle_shop && ../../.venv/bin/dbt docs generate --profiles-dir .

metricflow-check:
	uv run python scripts/verify_metricflow_duckdb.py

run-api:
	uv run uvicorn apps.api.main:app --reload --port 8000

run-ui:
	uv run streamlit run apps/ui/streamlit_app.py --server.port 8501

test:
	uv run pytest

lint:
	uv run ruff check .

typecheck:
	uv run mypy src apps scripts tests

check: lint typecheck test
