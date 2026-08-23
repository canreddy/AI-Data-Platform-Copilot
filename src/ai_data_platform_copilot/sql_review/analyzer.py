"""SQLGlot-backed deterministic SQL review orchestration."""

from __future__ import annotations

import time
from collections.abc import Iterable

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from ai_data_platform_copilot.domain.errors import (
    AmbiguousResourceError,
    ResourceNotFoundError,
    SnapshotNotFoundError,
)
from ai_data_platform_copilot.domain.models import MetadataResource
from ai_data_platform_copilot.domain.sql_review import (
    ExplanationStatus,
    FindingCategory,
    FindingSeverity,
    SQLFinding,
    SQLReviewRequest,
    SQLReviewResponse,
    SQLReviewSummary,
)
from ai_data_platform_copilot.ports.metadata_repository import MetadataRepository
from ai_data_platform_copilot.ports.sql_explanation import SQLExplanationProvider
from ai_data_platform_copilot.sql_review.rules import DEFAULT_RULES, RuleContext, SQLRule

SEVERITY_ORDER = {
    FindingSeverity.CRITICAL: 0,
    FindingSeverity.ERROR: 1,
    FindingSeverity.WARNING: 2,
    FindingSeverity.INFO: 3,
}


class SQLReviewService:
    """Parse and review SQL without executing or mutating it."""

    def __init__(
        self,
        repository: MetadataRepository | None = None,
        *,
        rules: Iterable[SQLRule] = DEFAULT_RULES,
        explanation_provider: SQLExplanationProvider | None = None,
    ) -> None:
        self._repository = repository
        self._rules = tuple(rules)
        self._explanation_provider = explanation_provider

    def review(self, request: SQLReviewRequest) -> SQLReviewResponse:
        started = time.perf_counter()
        limitations = [
            "No SQL was executed; findings are based on static analysis only.",
            "Bytes scanned and monetary cost require a BigQuery dry run and are not estimated in Phase 2.",
            "dbt artifacts do not expose reliable partition configuration or table cardinality, so partition-filter "
            "and high-cardinality checks are not asserted.",
        ]
        if request.governed_metric_sql:
            limitations.append(
                "Governed metric SQL should receive physical optimization only; semantic corrections belong in "
                "MetricFlow YAML."
            )
        try:
            parsed = parse(request.sql, read=request.dialect.value)
        except ParseError as error:
            parse_finding = self._parse_finding(error)
            response = self._response(
                request=request,
                started=started,
                valid_sql=False,
                read_only=False,
                statement_count=0,
                findings=(parse_finding,),
                resources=(),
                snapshot_id=None,
                limitations=limitations,
            )
            return self._with_explanation(request, response, started)

        statements = tuple(statement for statement in parsed if statement is not None)
        if not statements:
            finding = SQLFinding(
                rule_id="correctness.empty_sql",
                severity=FindingSeverity.ERROR,
                category=FindingCategory.CORRECTNESS,
                title="No SQL statement",
                message="The input contains no parseable SQL statement.",
                recommendation="Provide one complete SQL statement for review.",
                statement_index=0,
            )
            response = self._response(
                request=request,
                started=started,
                valid_sql=False,
                read_only=False,
                statement_count=0,
                findings=(finding,),
                resources=(),
                snapshot_id=None,
                limitations=limitations,
            )
            return self._with_explanation(request, response, started)

        snapshot_id, metadata_available = self._metadata_snapshot(request.snapshot_id)
        if not metadata_available:
            limitations.append("No active dbt metadata snapshot was available; table and column checks were skipped.")

        findings: list[SQLFinding] = []
        referenced: dict[str, MetadataResource] = {}
        if len(statements) > 1:
            findings.append(
                SQLFinding(
                    rule_id="safety.multiple_statements",
                    severity=FindingSeverity.ERROR,
                    category=FindingCategory.SAFETY,
                    title="Multiple SQL statements",
                    message=f"The input contains {len(statements)} statements, increasing review and execution risk.",
                    recommendation="Submit and review one statement at a time.",
                    statement_index=0,
                )
            )

        for index, statement in enumerate(statements):
            aliases, statement_resources = self._resolve_metadata(statement, snapshot_id)
            referenced.update((resource.unique_id, resource) for resource in statement_resources)
            context = RuleContext(
                statement=statement,
                statement_index=index,
                dialect=request.dialect,
                aliases=aliases,
            )
            for rule in self._rules:
                findings.extend(rule.evaluate(context))

        findings.sort(
            key=lambda finding: (
                SEVERITY_ORDER[finding.severity],
                finding.statement_index,
                finding.line or 0,
                finding.column or 0,
                finding.rule_id,
            )
        )
        response = self._response(
            request=request,
            started=started,
            valid_sql=True,
            read_only=all(isinstance(statement, exp.Query) for statement in statements),
            statement_count=len(statements),
            findings=tuple(findings),
            resources=tuple(sorted(referenced.values(), key=lambda resource: resource.unique_id)),
            snapshot_id=snapshot_id,
            limitations=limitations,
        )
        return self._with_explanation(request, response, started)

    def _with_explanation(
        self,
        request: SQLReviewRequest,
        response: SQLReviewResponse,
        started: float,
    ) -> SQLReviewResponse:
        if not request.include_explanation:
            return response
        if self._explanation_provider is None:
            return response.model_copy(
                update={
                    "explanation_status": ExplanationStatus.DISABLED,
                    "limitations": (*response.limitations, "Optional LLM explanation is disabled."),
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )
        try:
            explanation = self._explanation_provider.explain(response)
        except Exception:
            return response.model_copy(
                update={
                    "explanation_status": ExplanationStatus.ERROR,
                    "limitations": (
                        *response.limitations,
                        "Optional LLM explanation failed; deterministic findings remain authoritative.",
                    ),
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )
        return response.model_copy(
            update={
                "explanation_status": ExplanationStatus.GENERATED,
                "explanation": explanation,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        )

    def _metadata_snapshot(self, requested_snapshot_id: str | None) -> tuple[str | None, bool]:
        if self._repository is None:
            return None, False
        try:
            snapshot = self._repository.get_snapshot(requested_snapshot_id)
        except SnapshotNotFoundError:
            return None, False
        return snapshot.snapshot_id, True

    def _resolve_metadata(
        self, statement: exp.Expr, snapshot_id: str | None
    ) -> tuple[dict[str, MetadataResource], tuple[MetadataResource, ...]]:
        if self._repository is None or snapshot_id is None:
            return {}, ()
        cte_names = {cte.alias_or_name.casefold() for cte in statement.find_all(exp.CTE)}
        aliases: dict[str, MetadataResource] = {}
        resources: dict[str, MetadataResource] = {}
        for table in statement.find_all(exp.Table):
            if table.name.casefold() in cte_names:
                continue
            try:
                resource = self._repository.get_resource(table.name, snapshot_id=snapshot_id)
            except (ResourceNotFoundError, AmbiguousResourceError):
                continue
            resources[resource.unique_id] = resource
            aliases[table.name.casefold()] = resource
            aliases[table.alias_or_name.casefold()] = resource
        return aliases, tuple(resources.values())

    @staticmethod
    def _parse_finding(error: ParseError) -> SQLFinding:
        detail = error.errors[0] if error.errors else {}
        line = detail.get("line")
        column = detail.get("col")
        description = detail.get("description") or str(error)
        return SQLFinding(
            rule_id="correctness.parse_error",
            severity=FindingSeverity.ERROR,
            category=FindingCategory.CORRECTNESS,
            title="SQL parse error",
            message=str(description),
            recommendation="Correct the syntax for the explicitly selected dialect and submit it again.",
            statement_index=0,
            line=line if isinstance(line, int) else None,
            column=column if isinstance(column, int) else None,
        )

    @staticmethod
    def _response(
        *,
        request: SQLReviewRequest,
        started: float,
        valid_sql: bool,
        read_only: bool,
        statement_count: int,
        findings: tuple[SQLFinding, ...],
        resources: tuple[MetadataResource, ...],
        snapshot_id: str | None,
        limitations: list[str],
    ) -> SQLReviewResponse:
        counts = {severity: 0 for severity in FindingSeverity}
        for finding in findings:
            counts[finding.severity] += 1
        return SQLReviewResponse(
            dialect=request.dialect,
            valid_sql=valid_sql,
            read_only=read_only,
            statement_count=statement_count,
            findings=findings,
            summary=SQLReviewSummary(
                critical=counts[FindingSeverity.CRITICAL],
                error=counts[FindingSeverity.ERROR],
                warning=counts[FindingSeverity.WARNING],
                info=counts[FindingSeverity.INFO],
            ),
            referenced_resources=resources,
            metadata_snapshot_id=snapshot_id,
            limitations=tuple(limitations),
            governed_metric_sql=request.governed_metric_sql,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )
