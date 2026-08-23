"""Deterministic, composable SQLGlot review rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlglot import exp

from ai_data_platform_copilot.domain.models import EvidenceRef, MetadataResource
from ai_data_platform_copilot.domain.sql_review import (
    FindingCategory,
    FindingSeverity,
    SQLDialect,
    SQLFinding,
)


@dataclass(frozen=True)
class RuleContext:
    """Parsed statement plus conservative metadata resolution context."""

    statement: exp.Expr
    statement_index: int
    dialect: SQLDialect
    aliases: dict[str, MetadataResource]


class SQLRule(Protocol):
    """Static SQL rule contract."""

    rule_id: str

    def evaluate(self, context: RuleContext) -> tuple[SQLFinding, ...]: ...


def _location(node: exp.Expr) -> tuple[int | None, int | None]:
    line = node.meta.get("line")
    column = node.meta.get("col")
    return (line if isinstance(line, int) else None, column if isinstance(column, int) else None)


def _finding(
    context: RuleContext,
    node: exp.Expr,
    *,
    rule_id: str,
    severity: FindingSeverity,
    category: FindingCategory,
    title: str,
    message: str,
    recommendation: str,
    evidence: tuple[EvidenceRef, ...] = (),
) -> SQLFinding:
    line, column = _location(node)
    return SQLFinding(
        rule_id=rule_id,
        severity=severity,
        category=category,
        title=title,
        message=message,
        recommendation=recommendation,
        statement_index=context.statement_index,
        line=line,
        column=column,
        evidence=evidence,
    )


class ReadOnlyStatementRule:
    """Reject all statements that are not queries."""

    rule_id = "safety.non_read_only_statement"

    def evaluate(self, context: RuleContext) -> tuple[SQLFinding, ...]:
        if isinstance(context.statement, exp.Query):
            return ()
        return (
            _finding(
                context,
                context.statement,
                rule_id=self.rule_id,
                severity=FindingSeverity.CRITICAL,
                category=FindingCategory.SAFETY,
                title="Non-read-only statement",
                message=f"Statement {context.statement_index + 1} is {context.statement.key.upper()}, not a query.",
                recommendation="Remove all DDL and DML. The copilot accepts SQL for review only and never executes it.",
            ),
        )


class SelectStarRule:
    """Find wildcard projections without flagging COUNT(*)."""

    rule_id = "maintainability.select_star"

    def evaluate(self, context: RuleContext) -> tuple[SQLFinding, ...]:
        findings: list[SQLFinding] = []
        for select in context.statement.find_all(exp.Select):
            for projection in select.expressions:
                if isinstance(projection, exp.Star) or (
                    isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star)
                ):
                    findings.append(
                        _finding(
                            context,
                            projection,
                            rule_id=self.rule_id,
                            severity=FindingSeverity.WARNING,
                            category=FindingCategory.MAINTAINABILITY,
                            title="Wildcard projection",
                            message=(
                                f"Wildcard projection `{projection.sql(dialect=context.dialect.value)}` couples "
                                "output to schema changes."
                            ),
                            recommendation="List only the columns required by downstream consumers.",
                        )
                    )
        return tuple(findings)


class JoinPredicateRule:
    """Identify explicit and implicit Cartesian joins."""

    rule_id = "correctness.join_without_predicate"

    def evaluate(self, context: RuleContext) -> tuple[SQLFinding, ...]:
        findings: list[SQLFinding] = []
        for join in context.statement.find_all(exp.Join):
            kind = str(join.args.get("kind") or "").upper()
            if kind == "CROSS":
                title = "Explicit cross join"
                message = "CROSS JOIN produces every row combination and can grow results rapidly."
            elif join.args.get("on") is None and join.args.get("using") is None and join.args.get("method") is None:
                title = "Join without a predicate"
                message = "This join has no ON or USING predicate and behaves as a Cartesian product."
            else:
                continue
            findings.append(
                _finding(
                    context,
                    join,
                    rule_id=self.rule_id,
                    severity=FindingSeverity.ERROR,
                    category=FindingCategory.CORRECTNESS,
                    title=title,
                    message=message,
                    recommendation=(
                        "Add the intended key predicate, or document why a bounded Cartesian product is required."
                    ),
                )
            )
        return tuple(findings)


class NullComparisonRule:
    """Detect comparisons to NULL that always evaluate as unknown."""

    rule_id = "correctness.null_comparison"

    def evaluate(self, context: RuleContext) -> tuple[SQLFinding, ...]:
        findings: list[SQLFinding] = []
        for comparison_type in (exp.EQ, exp.NEQ):
            for comparison in context.statement.find_all(comparison_type):
                if isinstance(comparison.this, exp.Null) or isinstance(comparison.expression, exp.Null):
                    findings.append(
                        _finding(
                            context,
                            comparison,
                            rule_id=self.rule_id,
                            severity=FindingSeverity.ERROR,
                            category=FindingCategory.CORRECTNESS,
                            title="Invalid NULL comparison",
                            message="Equality and inequality comparisons to NULL do not return true in SQL.",
                            recommendation="Use IS NULL or IS NOT NULL.",
                        )
                    )
        return tuple(findings)


class NotInSubqueryRule:
    """Warn about NULL-sensitive NOT IN subqueries."""

    rule_id = "correctness.not_in_subquery"

    def evaluate(self, context: RuleContext) -> tuple[SQLFinding, ...]:
        findings: list[SQLFinding] = []
        for not_expression in context.statement.find_all(exp.Not):
            in_expression = not_expression.this
            if isinstance(in_expression, exp.In) and in_expression.args.get("query") is not None:
                findings.append(
                    _finding(
                        context,
                        not_expression,
                        rule_id=self.rule_id,
                        severity=FindingSeverity.WARNING,
                        category=FindingCategory.CORRECTNESS,
                        title="NULL-sensitive NOT IN",
                        message="NOT IN can return no rows when the subquery contains NULL.",
                        recommendation=(
                            "Prefer NOT EXISTS with an explicit correlated predicate, or exclude NULLs in the subquery."
                        ),
                    )
                )
        return tuple(findings)


class DivisionByZeroRule:
    """Detect a literal zero denominator."""

    rule_id = "correctness.literal_division_by_zero"

    def evaluate(self, context: RuleContext) -> tuple[SQLFinding, ...]:
        return tuple(
            _finding(
                context,
                division,
                rule_id=self.rule_id,
                severity=FindingSeverity.ERROR,
                category=FindingCategory.CORRECTNESS,
                title="Literal division by zero",
                message="The denominator is the numeric literal zero.",
                recommendation="Correct the expression or guard a variable denominator with NULLIF or SAFE_DIVIDE.",
            )
            for division in context.statement.find_all(exp.Div)
            if isinstance(division.expression, exp.Literal)
            and not division.expression.is_string
            and division.expression.this in {"0", "0.0"}
        )


class DistinctRule:
    """Highlight potentially expensive deduplication."""

    rule_id = "performance.distinct"

    def evaluate(self, context: RuleContext) -> tuple[SQLFinding, ...]:
        return tuple(
            _finding(
                context,
                select,
                rule_id=self.rule_id,
                severity=FindingSeverity.INFO,
                category=FindingCategory.PERFORMANCE,
                title="DISTINCT requires deduplication",
                message="DISTINCT can require a global shuffle or sort and may hide duplicate-producing joins.",
                recommendation=(
                    "Confirm duplicates are expected; otherwise correct the join grain before deduplicating."
                ),
            )
            for select in context.statement.find_all(exp.Select)
            if select.args.get("distinct") is not None
        )


class OrderWithoutLimitRule:
    """Find final sorts that are not paired with a result bound."""

    rule_id = "performance.order_without_limit"

    def evaluate(self, context: RuleContext) -> tuple[SQLFinding, ...]:
        if not isinstance(context.statement, exp.Query):
            return ()
        order = context.statement.args.get("order")
        if order is None or context.statement.args.get("limit") is not None:
            return ()
        return (
            _finding(
                context,
                order,
                rule_id=self.rule_id,
                severity=FindingSeverity.WARNING,
                category=FindingCategory.PERFORMANCE,
                title="Unbounded final sort",
                message="The final result is ordered without a LIMIT, which may sort the full result set.",
                recommendation="Remove presentation-only ordering or apply a justified row limit.",
            ),
        )


class BigQueryUnboundedScanRule:
    """Flag a provably filter-free top-level BigQuery table scan."""

    rule_id = "cost.bigquery_unbounded_scan"

    def evaluate(self, context: RuleContext) -> tuple[SQLFinding, ...]:
        if context.dialect is not SQLDialect.BIGQUERY or not isinstance(context.statement, exp.Query):
            return ()
        if not any(context.statement.find_all(exp.Table)):
            return ()
        if context.statement.args.get("where") is not None:
            return ()
        return (
            _finding(
                context,
                context.statement,
                rule_id=self.rule_id,
                severity=FindingSeverity.WARNING,
                category=FindingCategory.COST,
                title="Filter-free BigQuery scan",
                message="The top-level query reads tables without a WHERE clause. LIMIT does not reduce bytes read.",
                recommendation=(
                    "Add a selective predicate—preferably on the actual partition column—or confirm the full scan "
                    "is intentional."
                ),
            ),
        )


class QualifiedColumnMetadataRule:
    """Validate qualified columns only when their table alias is resolved."""

    rule_id = "correctness.unknown_qualified_column"

    def evaluate(self, context: RuleContext) -> tuple[SQLFinding, ...]:
        findings: list[SQLFinding] = []
        seen: set[tuple[str, str]] = set()
        for column in context.statement.find_all(exp.Column):
            if isinstance(column.this, exp.Star) or not column.table:
                continue
            resource = context.aliases.get(column.table.casefold())
            if resource is None:
                continue
            key = (resource.unique_id, column.name.casefold())
            if key in seen:
                continue
            seen.add(key)
            known_columns = {known.name.casefold() for known in resource.columns}
            if column.name.casefold() in known_columns:
                continue
            findings.append(
                _finding(
                    context,
                    column,
                    rule_id=self.rule_id,
                    severity=FindingSeverity.ERROR,
                    category=FindingCategory.CORRECTNESS,
                    title="Unknown qualified column",
                    message=(
                        f"`{column.sql(dialect=context.dialect.value)}` is not documented on dbt resource "
                        f"`{resource.name}`."
                    ),
                    recommendation=(
                        "Correct the column name or regenerate dbt catalog metadata if the warehouse schema changed."
                    ),
                    evidence=resource.evidence,
                )
            )
        return tuple(findings)


DEFAULT_RULES: tuple[SQLRule, ...] = (
    ReadOnlyStatementRule(),
    SelectStarRule(),
    JoinPredicateRule(),
    NullComparisonRule(),
    NotInSubqueryRule(),
    DivisionByZeroRule(),
    DistinctRule(),
    OrderWithoutLimitRule(),
    BigQueryUnboundedScanRule(),
    QualifiedColumnMetadataRule(),
)
