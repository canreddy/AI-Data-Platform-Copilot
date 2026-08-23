# Demo guide

1. Run `make sync dbt-build dbt-docs check`.
2. Start `make run-api`, then `make run-ui` in another terminal.
3. Search for `customer_id` in Metadata explorer.
4. Inspect upstream `customers` and downstream impact from `stg_payments` in Lineage explorer.
5. Review `select * from orders` and confirm SQL is analyzed but never executed.
6. Open Metrics explorer, select `total_revenue`, group by `metric_time__month`, and compile.
7. Confirm the read-only demo execution and inspect its bounded rows and execution evidence.
8. With a key, ask “What was revenue in 2018?”, confirm execution, and verify the governed result is `1672.0`.
9. Without an OpenAI key, show Copilot's disabled state. With a key, ask “What metrics are available?” and inspect
   the deterministic tool evidence beneath the composed answer.
