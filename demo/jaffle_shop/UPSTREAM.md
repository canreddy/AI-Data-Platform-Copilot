# Upstream provenance

- Repository: https://github.com/dbt-labs/jaffle_shop_duckdb
- Branch at incorporation: `duckdb`
- Pinned commit: `36bde6cba69d962b83be1d52fc65a0dce1cb4ebb`
- Upstream commit date: 2026-03-02
- Incorporated: 2026-08-20
- License: Apache-2.0; retained in `LICENSE`

## Local modifications

- Added a payment-grain `payments` model so governed payment metrics use real dbt model columns and retain order date.
- Added current-spec semantic models, measures, entities, dimensions, and metrics in `models/semantic_models.yml`.
- Added schema documentation and tests for the local `payments` model.
- Added the current-spec daily time spine required by dbt semantic validation.
- Updated the deprecated upstream `dbt_modules` clean target to `dbt_packages` for dbt 1.11.
- Generated artifacts and the DuckDB database remain build outputs and are not committed.
