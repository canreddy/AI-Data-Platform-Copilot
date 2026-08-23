"""Isolated, read-only execution for server-compiled demo metric SQL."""

from __future__ import annotations

import multiprocessing
import time
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

import duckdb
import sqlglot
from sqlglot import expressions

from ai_data_platform_copilot.domain.errors import MetricExecutionError
from ai_data_platform_copilot.domain.metrics import MetricExecutionResult, MetricQueryCompilation

_PROHIBITED = (
    expressions.Alter,
    expressions.Command,
    expressions.Create,
    expressions.Delete,
    expressions.Drop,
    expressions.Insert,
    expressions.Merge,
    expressions.Update,
)


def _validate_read_only_sql(sql: str) -> None:
    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.ParseError as error:
        raise MetricExecutionError("Compiled metric SQL could not be validated") from error
    if len(statements) != 1 or not isinstance(statements[0], expressions.Query):
        raise MetricExecutionError("Execution requires exactly one read-only query")
    if any(statements[0].find(kind) is not None for kind in _PROHIBITED):
        raise MetricExecutionError("Compiled metric SQL contains a prohibited operation")


def _execute_child(database: str, sql: str, max_rows: int, connection: Connection) -> None:
    try:
        duckdb_connection = duckdb.connect(database, read_only=True)
        try:
            duckdb_connection.execute("SET enable_external_access = false")
            duckdb_connection.execute("SET threads = 1")
            duckdb_connection.execute("SET memory_limit = '256MB'")
            bounded_sql = sql.rstrip().removesuffix(";")
            cursor = duckdb_connection.execute(
                f"SELECT * FROM ({bounded_sql}) AS governed_metric_result LIMIT {max_rows + 1}"
            )
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            connection.send({"columns": columns, "rows": rows})
        finally:
            duckdb_connection.close()
    except Exception as error:  # pragma: no cover - exercised through parent process
        connection.send({"error": f"{type(error).__name__}: {error}"})
    finally:
        connection.close()


class DuckDBDemoMetricExecutor:
    """Execute only a fresh server-owned MetricFlow compilation on the included database."""

    def __init__(self, *, database_path: Path, timeout_seconds: int = 5, max_rows: int = 100) -> None:
        self._database_path = database_path.resolve()
        self._timeout_seconds = timeout_seconds
        self._max_rows = max_rows

    def execute(self, compilation: MetricQueryCompilation) -> MetricExecutionResult:
        if not compilation.validation.valid or not compilation.sql or compilation.executed:
            raise MetricExecutionError("Only a fresh, valid, unexecuted MetricFlow compilation may run")
        if self._database_path.name != "jaffle_shop.duckdb" or not self._database_path.is_file():
            raise MetricExecutionError("The included Jaffle Shop DuckDB database is unavailable")
        _validate_read_only_sql(compilation.sql)
        started = time.perf_counter()
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        process = context.Process(
            target=_execute_child,
            args=(str(self._database_path), compilation.sql, self._max_rows, child),
        )
        process.start()
        child.close()
        try:
            if not parent.poll(self._timeout_seconds):
                process.terminate()
                process.join(timeout=1)
                raise MetricExecutionError(f"Metric execution exceeded {self._timeout_seconds} seconds")
            payload: dict[str, Any] = parent.recv()
        finally:
            parent.close()
            process.join(timeout=1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
        if "error" in payload:
            raise MetricExecutionError(f"Read-only demo execution failed: {payload['error']}")
        columns = tuple(str(column) for column in payload["columns"])
        raw_rows = payload["rows"]
        truncated = len(raw_rows) > self._max_rows
        rows = tuple(dict(zip(columns, row, strict=True)) for row in raw_rows[: self._max_rows])
        return MetricExecutionResult(
            compilation=compilation,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            database="demo/jaffle_shop/jaffle_shop.duckdb",
            max_rows=self._max_rows,
            timeout_seconds=self._timeout_seconds,
            evidence=compilation.evidence,
        )
