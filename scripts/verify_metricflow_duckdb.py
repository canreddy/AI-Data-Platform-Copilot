"""Verify the pinned MetricFlow stack against the included DuckDB demo.

This script is a development-only compatibility check. It is deliberately not
part of the application API and accepts no user-provided SQL.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import duckdb
from sqlglot import exp, parse

ROOT = Path(__file__).resolve().parents[1]
PROJECT_DIR = ROOT / "demo" / "jaffle_shop"
DATABASE_PATH = PROJECT_DIR / "jaffle_shop.duckdb"
MF_PATH = ROOT / ".venv" / "bin" / "mf"
COMMAND_TIMEOUT_SECONDS = 30
QUERY_TIMEOUT_SECONDS = 10

PROHIBITED_EXPRESSIONS = (
    exp.Alter,
    exp.Command,
    exp.Create,
    exp.Delete,
    exp.Drop,
    exp.Insert,
    exp.Merge,
    exp.Update,
)


def validate_read_only_sql(sql: str) -> None:
    """Require exactly one parseable query with no mutating expressions."""
    statements = parse(sql, read="duckdb")
    if len(statements) != 1 or not isinstance(statements[0], exp.Query):
        raise ValueError("MetricFlow compilation must produce exactly one query statement")
    if any(statements[0].find(expression_type) is not None for expression_type in PROHIBITED_EXPRESSIONS):
        raise ValueError("MetricFlow compilation contained a prohibited SQL operation")


def run_command(arguments: list[str], *, timeout: int = COMMAND_TIMEOUT_SECONDS) -> str:
    """Run one fixed compatibility command and return its standard output."""
    try:
        result = subprocess.run(
            arguments,
            cwd=PROJECT_DIR,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"Compatibility command failed with exit code {error.returncode}: "
            f"{error.stderr.strip() or error.stdout.strip()}"
        ) from error
    return result.stdout.strip()


def execute_compiled_sql(sql_path: Path) -> dict[str, Any]:
    """Execute prevalidated SQL through a read-only DuckDB connection."""
    sql = sql_path.read_text(encoding="utf-8")
    validate_read_only_sql(sql)
    connection = duckdb.connect(str(DATABASE_PATH), read_only=True)
    try:
        cursor = connection.execute(sql)
        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description]
    finally:
        connection.close()
    return {"columns": columns, "row_count": len(rows)}


def verify() -> dict[str, Any]:
    """Run semantic validation, discovery, compilation, and isolated execution."""
    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(f"Demo database does not exist: {DATABASE_PATH}. Run `make dbt-build` first.")
    if not MF_PATH.is_file():
        raise FileNotFoundError(f"MetricFlow CLI does not exist: {MF_PATH}. Run `make sync` first.")

    validation = run_command([str(MF_PATH), "validate-configs", "--skip-dw", "--show-all"])
    metrics = run_command([str(MF_PATH), "list", "metrics", "--show-all-dimensions"])
    dimensions = run_command([str(MF_PATH), "list", "dimensions", "--metrics", "total_revenue"])
    compiled_sql = run_command(
        [
            str(MF_PATH),
            "query",
            "--metrics",
            "total_revenue",
            "--group-by",
            "metric_time__month",
            "--explain",
            "--quiet",
        ]
    )
    validate_read_only_sql(compiled_sql)

    target_dir = PROJECT_DIR / "target"
    target_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", dir=target_dir, encoding="utf-8") as sql_file:
        sql_file.write(compiled_sql)
        sql_file.flush()
        execution_output = run_command(
            [sys.executable, str(Path(__file__).resolve()), "--execute-file", sql_file.name],
            timeout=QUERY_TIMEOUT_SECONDS,
        )

    return {
        "versions": {
            "python": ".".join(str(part) for part in sys.version_info[:3]),
            "dbt-core": importlib.metadata.version("dbt-core"),
            "dbt-duckdb": importlib.metadata.version("dbt-duckdb"),
            "dbt-metricflow": importlib.metadata.version("dbt-metricflow"),
            "metricflow": importlib.metadata.version("metricflow"),
            "duckdb": importlib.metadata.version("duckdb"),
        },
        "semantic_validation_passed": "ERRORS: 0" in validation,
        "metric_discovery_passed": all(
            metric_name in metrics for metric_name in ("customers", "orders", "total_revenue", "average_order_value")
        ),
        "dimension_discovery_passed": "payment__payment_method" in dimensions and "metric_time" in dimensions,
        "compiled_sql": compiled_sql,
        "execution": json.loads(execution_output),
        "safety": {
            "database": str(DATABASE_PATH.relative_to(ROOT)),
            "connection_mode": "read_only",
            "statement_policy": "single query only",
            "timeout_seconds": QUERY_TIMEOUT_SECONDS,
        },
    }


def main() -> None:
    """Run the compatibility check or its isolated read-only execution child."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-file", type=Path, help=argparse.SUPPRESS)
    arguments = parser.parse_args()

    if arguments.execute_file is not None:
        print(json.dumps(execute_compiled_sql(arguments.execute_file), sort_keys=True))
        return

    result = verify()
    if not all(
        result[key]
        for key in ("semantic_validation_passed", "metric_discovery_passed", "dimension_discovery_passed")
    ):
        raise RuntimeError(f"Compatibility check failed: {json.dumps(result, sort_keys=True)}")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
