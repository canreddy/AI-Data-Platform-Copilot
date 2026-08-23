from pathlib import Path

import pytest

from ai_data_platform_copilot.adapters.dbt.artifacts import load_artifact_snapshot
from ai_data_platform_copilot.adapters.sqlite.repository import SQLiteMetadataRepository
from ai_data_platform_copilot.domain.sql_review import (
    ExplanationStatus,
    FindingSeverity,
    SQLDialect,
    SQLExplanation,
    SQLReviewRequest,
    SQLReviewResponse,
)
from ai_data_platform_copilot.sql_review.analyzer import SQLReviewService

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def reviewer(tmp_path: Path) -> SQLReviewService:
    repository = SQLiteMetadataRepository(tmp_path / "metadata.sqlite3")
    repository.ingest(load_artifact_snapshot(ROOT / "demo" / "jaffle_shop" / "target"))
    return SQLReviewService(repository)


def rule_ids(response: SQLReviewResponse) -> set[str]:
    return {finding.rule_id for finding in response.findings}


def test_clean_bounded_query_has_no_findings(reviewer: SQLReviewService) -> None:
    response = reviewer.review(
        SQLReviewRequest(
            sql="""
                select o.order_id, o.customer_id
                from orders as o
                where o.order_date >= date '2018-01-01'
                limit 100
            """,
            dialect=SQLDialect.BIGQUERY,
        )
    )

    assert response.valid_sql is True
    assert response.read_only is True
    assert response.findings == ()
    assert [resource.name for resource in response.referenced_resources] == ["orders"]


def test_count_star_is_not_a_wildcard_projection(reviewer: SQLReviewService) -> None:
    response = reviewer.review(
        SQLReviewRequest(
            sql="select count(*) from orders where order_date >= date '2018-01-01'",
            dialect=SQLDialect.BIGQUERY,
        )
    )

    assert "maintainability.select_star" not in rule_ids(response)


def test_detects_wildcard_and_join_without_predicate(reviewer: SQLReviewService) -> None:
    response = reviewer.review(
        SQLReviewRequest(sql="select o.* from orders o join customers c", dialect=SQLDialect.BIGQUERY)
    )

    assert rule_ids(response) >= {
        "maintainability.select_star",
        "correctness.join_without_predicate",
        "cost.bigquery_unbounded_scan",
    }


@pytest.mark.parametrize(
    ("sql", "expected_rule"),
    [
        ("select order_id from orders where status = null", "correctness.null_comparison"),
        (
            "select order_id from orders where order_id not in (select order_id from payments)",
            "correctness.not_in_subquery",
        ),
        ("select 1 / 0", "correctness.literal_division_by_zero"),
        ("select distinct customer_id from orders", "performance.distinct"),
        ("select order_id from orders order by order_id", "performance.order_without_limit"),
    ],
)
def test_correctness_and_performance_rules(reviewer: SQLReviewService, sql: str, expected_rule: str) -> None:
    response = reviewer.review(SQLReviewRequest(sql=sql, dialect=SQLDialect.BIGQUERY))

    assert expected_rule in rule_ids(response)


def test_non_read_only_and_multiple_statements_are_critical_or_errors(reviewer: SQLReviewService) -> None:
    response = reviewer.review(SQLReviewRequest(sql="select 1; delete from orders", dialect=SQLDialect.DUCKDB))

    assert response.read_only is False
    assert response.statement_count == 2
    assert rule_ids(response) >= {"safety.multiple_statements", "safety.non_read_only_statement"}
    assert any(finding.severity is FindingSeverity.CRITICAL for finding in response.findings)


def test_invalid_sql_returns_structured_parse_finding(reviewer: SQLReviewService) -> None:
    response = reviewer.review(SQLReviewRequest(sql="select from", dialect=SQLDialect.BIGQUERY))

    assert response.valid_sql is False
    assert response.findings[0].rule_id == "correctness.parse_error"


def test_qualified_column_validation_uses_dbt_evidence(reviewer: SQLReviewService) -> None:
    response = reviewer.review(
        SQLReviewRequest(
            sql="select o.not_a_column from orders o where o.order_date >= date '2018-01-01'",
            dialect=SQLDialect.BIGQUERY,
        )
    )

    finding = next(
        finding for finding in response.findings if finding.rule_id == "correctness.unknown_qualified_column"
    )
    assert finding.evidence[0].unique_id == "model.jaffle_shop.orders"
    assert finding.evidence[0].file_path == "models/orders.sql"


def test_duckdb_dialect_does_not_apply_bigquery_scan_rule(reviewer: SQLReviewService) -> None:
    response = reviewer.review(SQLReviewRequest(sql="select order_id from orders", dialect=SQLDialect.DUCKDB))

    assert "cost.bigquery_unbounded_scan" not in rule_ids(response)
    assert response.dialect is SQLDialect.DUCKDB


def test_bigquery_limit_does_not_suppress_scan_warning(reviewer: SQLReviewService) -> None:
    response = reviewer.review(
        SQLReviewRequest(sql="select order_id from orders limit 10", dialect=SQLDialect.BIGQUERY)
    )

    assert "cost.bigquery_unbounded_scan" in rule_ids(response)


def test_natural_join_is_not_mislabeled_as_cartesian(reviewer: SQLReviewService) -> None:
    response = reviewer.review(
        SQLReviewRequest(
            sql="select o.order_id from orders o natural join payments p where o.order_date >= date '2018-01-01'",
            dialect=SQLDialect.DUCKDB,
        )
    )

    assert "correctness.join_without_predicate" not in rule_ids(response)


def test_cte_alias_does_not_create_false_unknown_column(reviewer: SQLReviewService) -> None:
    response = reviewer.review(
        SQLReviewRequest(
            sql="""
                with recent as (
                    select order_id from orders where order_date >= date '2018-01-01'
                )
                select r.order_id from recent r limit 10
            """,
            dialect=SQLDialect.BIGQUERY,
        )
    )

    assert "correctness.unknown_qualified_column" not in rule_ids(response)


def test_limitations_are_honest_about_unavailable_cost_metadata(reviewer: SQLReviewService) -> None:
    response = reviewer.review(SQLReviewRequest(sql="select 1", dialect=SQLDialect.BIGQUERY))

    assert any("Bytes scanned" in limitation for limitation in response.limitations)
    assert any("partition" in limitation for limitation in response.limitations)


class RecordingExplanationProvider:
    def __init__(self) -> None:
        self.reviews: list[SQLReviewResponse] = []

    def explain(self, review: SQLReviewResponse) -> SQLExplanation:
        self.reviews.append(review)
        return SQLExplanation(
            text="Explanation derived from deterministic findings.",
            model="test-model",
            response_id="response-test",
            based_on_rule_ids=tuple(finding.rule_id for finding in review.findings),
            input_tokens=10,
            output_tokens=5,
        )


def test_optional_explanation_receives_only_completed_review(tmp_path: Path) -> None:
    repository = SQLiteMetadataRepository(tmp_path / "metadata.sqlite3")
    repository.ingest(load_artifact_snapshot(ROOT / "demo" / "jaffle_shop" / "target"))
    provider = RecordingExplanationProvider()
    service = SQLReviewService(repository, explanation_provider=provider)

    response = service.review(
        SQLReviewRequest(
            sql="select * from orders",
            dialect=SQLDialect.BIGQUERY,
            include_explanation=True,
        )
    )

    assert response.explanation_status is ExplanationStatus.GENERATED
    assert response.explanation is not None
    assert len(provider.reviews) == 1
    assert provider.reviews[0].explanation is None
    assert response.explanation.based_on_rule_ids == tuple(finding.rule_id for finding in response.findings)


def test_requested_explanation_is_disabled_without_provider(reviewer: SQLReviewService) -> None:
    response = reviewer.review(SQLReviewRequest(sql="select 1", include_explanation=True, dialect=SQLDialect.BIGQUERY))

    assert response.explanation_status is ExplanationStatus.DISABLED
    assert response.explanation is None
