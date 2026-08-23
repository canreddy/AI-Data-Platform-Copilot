# Phase 0 compatibility report

Verified on 2026-08-20 on macOS arm64. Dependencies are locked in `uv.lock`; the versions below are direct runtime
pins or resolved transitive runtime pins.

## Version matrix

| Component | Version | Status |
|---|---:|---|
| Python | 3.13.7 | Pass |
| dbt Core | 1.11.13 | Pass |
| dbt DuckDB adapter | 1.10.1 | Pass |
| dbt MetricFlow CLI | 0.14.0 | Pass |
| MetricFlow engine | 0.212.0 | Pass |
| DuckDB Python package/engine | 1.5.5 | Pass |

The upstream `dbt-core==1.11.0` release was not selected because PyPI marks it as yanked. The current non-yanked
1.11 patch release resolved compatibly with the pinned DuckDB adapter and MetricFlow CLI.

## Vendored demo

`demo/jaffle_shop` is pinned to dbt Labs' `jaffle_shop_duckdb` commit
`36bde6cba69d962b83be1d52fc65a0dce1cb4ebb` from the `duckdb` branch. The upstream Apache-2.0 license is retained,
and `demo/jaffle_shop/UPSTREAM.md` records the incorporation date and local changes.

The local semantic layer contains exactly three semantic models (`customers`, `orders`, and `payments`) and four
public metrics (`customers`, `orders`, `total_revenue`, and `average_order_value`). A local payment-grain model was
needed because the upstream project exposes payments only as a staging view and the governed revenue scenarios need
payment method plus order date. A daily time-spine model was also required by dbt 1.11 semantic validation.

## Commands executed

The repeatable successful sequence is:

```shell
uv python install 3.13.7
uv lock --python 3.13.7
uv sync --frozen
cd demo/jaffle_shop
../../.venv/bin/dbt clean --profiles-dir .
../../.venv/bin/dbt build --profiles-dir .
../../.venv/bin/dbt docs generate --profiles-dir .
cd ../..
UV_CACHE_DIR=.uv-cache uv run python scripts/verify_metricflow_duckdb.py
UV_CACHE_DIR=.uv-cache uv run ruff check .
UV_CACHE_DIR=.uv-cache uv run mypy scripts tests
UV_CACHE_DIR=.uv-cache uv run pytest
```

The compatibility script runs the equivalent of these MetricFlow operations from the demo project:

```shell
mf validate-configs --skip-dw --show-all
mf list metrics --show-all-dimensions
mf list dimensions --metrics total_revenue
mf query --metrics total_revenue --group-by metric_time__month --explain --quiet
```

## Results

- `dbt build`: pass — 35/35 operations; 7 models, 3 seeds, and 25 data tests; no warnings or errors.
- `dbt docs generate`: pass — generated `manifest.json`, `catalog.json`, `run_results.json`, and
  `semantic_manifest.json` under the ignored `demo/jaffle_shop/target` directory.
- MetricFlow semantic validation: pass — 0 errors, 0 future errors, and 0 warnings.
- Metric discovery: pass — exactly the four intended public metrics were listed.
- Dimension discovery: pass — `total_revenue` supports `metric_time`, customer/order dimensions, and
  `payment__payment_method`.
- Governed SQL compilation: pass — monthly `total_revenue` compiled to DuckDB SQL using `DATE_TRUNC`, `SUM(amount)`,
  and the payment model.
- Isolated execution verification: pass — the compiled query returned four monthly rows with columns
  `metric_time__month` and `total_revenue`.

## Execution safety boundary

Phase 0 originally restricted execution to `scripts/verify_metricflow_duckdb.py`. The separately approved Phase 3.1
product path reuses the same principles for explicitly confirmed governed metric requests only; no endpoint accepts
SQL. The compatibility script has all of these guards:

- fixed metric request; no user-supplied SQL;
- included database path only: `demo/jaffle_shop/jaffle_shop.duckdb`;
- SQLGlot validation requiring exactly one query and rejecting mutation/DDL nodes;
- DuckDB opened with `read_only=True`;
- execution isolated in a child process with a 10-second timeout;
- no import or route from application code.

## Compatibility issues encountered

1. dbt 1.11 requires a daily-or-finer time-spine model whenever semantic models are present. A DuckDB-native daily
   spine was added.
2. dbt semantic validation uses a process pool and queries the operating-system semaphore limit. The managed coding
   sandbox blocked that system call, so dbt/MetricFlow semantic commands required approved execution outside that
   sandbox. This is an environment restriction, not an application/runtime incompatibility.
3. DuckDB profile paths are relative to the command working directory. All Make targets now enter
   `demo/jaffle_shop` before invoking dbt, ensuring dbt and MetricFlow use the same included database.

## Architecture deviations and consequences

- No approved architecture component was removed or replaced.
- The semantic layer adds one payment-grain dbt model and one time-spine dbt model to the pinned upstream snapshot.
- MetricFlow's CLI is confirmed as a viable adapter boundary for DuckDB with this lock set. Phase 3 can implement the
  provider using argument-array subprocess calls and structured output/capability errors as planned.
- Generated dbt artifacts and the DuckDB database remain reproducible, ignored build outputs rather than committed
  binaries. The future demo bootstrap command must generate them before starting the application.

## Updated implementation plan

Phase 1 can proceed without a MetricFlow fallback limitation. It should ingest `manifest.json` and `catalog.json`
from one completed build into immutable SQLite/FTS5 snapshots, then build confirmed model-level graph edges from the
same manifest checksum. Semantic nodes can be read from `semantic_manifest.json` when metric-aware lineage is added
in Phase 3. The remaining approved phase boundaries are unchanged.
