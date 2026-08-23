FROM python:3.13.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_NO_DEV=1
WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y graphviz \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.12.3

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

COPY apps ./apps
COPY demo ./demo
COPY scripts ./scripts
RUN cd demo/jaffle_shop \
    && /app/.venv/bin/dbt build --profiles-dir . \
    && /app/.venv/bin/dbt docs generate --profiles-dir .

ENV PATH="/app/.venv/bin:$PATH" \
    COPILOT_METADATA_DB=/app/data/metadata.sqlite3 \
    COPILOT_ARTIFACT_DIR=/app/demo/jaffle_shop/target \
    COPILOT_DBT_PROJECT_DIR=/app/demo/jaffle_shop \
    COPILOT_METRICFLOW_EXECUTABLE=/app/.venv/bin/mf
