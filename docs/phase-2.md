# Phase 2: deterministic SQL review

## Outcome

Phase 2 adds static SQL review for explicitly selected BigQuery and DuckDB dialects. SQL is parsed into an AST with
SQLGlot and is never executed. The review works offline; an optional OpenAI Responses API provider may explain the
already-complete deterministic result when `OPENAI_API_KEY` is configured.

## Deterministic rules

| Rule ID | Severity | Purpose |
|---|---|---|
| `safety.non_read_only_statement` | critical | Identifies DDL, DML, and other non-query statements. |
| `safety.multiple_statements` | error | Requires statements to be reviewed independently. |
| `correctness.join_without_predicate` | error | Identifies explicit or implicit Cartesian joins. |
| `correctness.null_comparison` | error | Identifies `= NULL` and `!= NULL`. |
| `correctness.not_in_subquery` | warning | Highlights NULL-sensitive `NOT IN` behavior. |
| `correctness.literal_division_by_zero` | error | Detects a literal zero denominator. |
| `correctness.unknown_qualified_column` | error | Checks qualified columns against resolved dbt resources. |
| `maintainability.select_star` | warning | Finds wildcard projections without flagging `COUNT(*)`. |
| `performance.distinct` | info | Highlights global deduplication and possible grain problems. |
| `performance.order_without_limit` | warning | Finds unbounded final sorts. |
| `cost.bigquery_unbounded_scan` | warning | Finds top-level BigQuery table reads without a `WHERE` clause. |

Natural joins are not mislabelled as Cartesian joins. CTE aliases are not treated as physical dbt resources. Qualified
column validation runs only when an alias is conservatively resolved to one dbt resource.

## Metadata awareness

Physical table names are resolved against the selected immutable metadata snapshot. Resolved resources are returned
with their manifest evidence. Qualified columns such as `o.not_a_column` are validated only when `o` maps to a known
resource. Unresolved external tables and derived/CTE aliases are not called incorrect.

dbt artifacts do not reliably provide BigQuery partition configuration, table cardinality, or current storage bytes.
The API therefore reports those checks as limitations instead of inventing partition, high-cardinality, scan-size, or
cost findings. A future BigQuery dry-run adapter can supply those facts without changing the deterministic contracts.

## Safety boundary

- The endpoint parses strings but contains no warehouse or DuckDB execution adapter.
- Every non-query statement receives a critical finding.
- Multiple statements receive an error even when every statement is a query.
- The UI and API provide review only; there is no execute action.
- Tests submit `DROP TABLE` and verify metadata remains unchanged.

## Optional explanation

`include_explanation=true` requests an explanation. Without `OPENAI_API_KEY`, the result is returned with status
`disabled`. With a key, the provider sends only the deterministic findings, evidence, dialect, safety flags, and
limitations to the OpenAI Responses API. It does not send the submitted SQL and cannot add, remove, or weaken rules.
The provider uses `store=false`, a bounded timeout, and a configurable `OPENAI_MODEL` (default `gpt-5.4-mini`). The
deterministic result remains available if the request fails. See the
[official Responses API documentation](https://developers.openai.com/api/reference/resources/responses/methods/create).

For governed metric SQL, the explanation prompt permits physical optimization advice but directs semantic changes to
MetricFlow YAML.

## API

`POST /api/v1/sql/reviews`

Example:

```json
{
  "sql": "select o.* from orders o join customers c",
  "dialect": "bigquery",
  "include_explanation": false,
  "governed_metric_sql": false
}
```

The response includes parse validity, read-only status, statement count, ordered findings, severity counts, resolved
dbt resources, evidence, limitations, explanation status, and total review latency.

## UI

The SQL Reviewer page batches SQL, dialect, governed-metric status, and explanation preference in a Streamlit form.
Results are grouped into a severity summary, deterministic finding cards, resolved resources, and limitations.

Run the API and UI with:

```shell
make run-api
make run-ui
```

Use `demo/sql_samples/inefficient_bigquery.sql` for the initial demonstration.

## Current limitations

- No query execution or BigQuery dry run.
- No byte or monetary cost estimate.
- No schema inference for unresolved external tables.
- No proof of join cardinality without table statistics.
- No automatic SQL rewrite.
- The optional explanation is prose only and has no authority over findings.

