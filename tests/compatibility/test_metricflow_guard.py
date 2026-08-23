from pathlib import Path

import pytest

from scripts.verify_metricflow_duckdb import execute_compiled_sql, validate_read_only_sql


@pytest.mark.parametrize(
    "sql",
    [
        "delete from payments",
        "create table unsafe as select 1",
        "select 1; select 2",
    ],
)
def test_rejects_non_read_only_or_multiple_statements(sql: str) -> None:
    with pytest.raises(ValueError):
        validate_read_only_sql(sql)


def test_accepts_single_select() -> None:
    validate_read_only_sql("select date_trunc('month', order_date) from payments")


def test_execution_revalidates_sql(tmp_path: Path) -> None:
    sql_path = tmp_path / "unsafe.sql"
    sql_path.write_text("drop table payments", encoding="utf-8")
    with pytest.raises(ValueError):
        execute_compiled_sql(sql_path)
