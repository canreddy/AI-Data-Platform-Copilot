"""Controlled natural-language routing over deterministic services."""

from __future__ import annotations

import re
from datetime import date
from difflib import get_close_matches
from typing import Any

from ai_data_platform_copilot.application.metric_service import MetricService
from ai_data_platform_copilot.application.services import MetadataService
from ai_data_platform_copilot.domain.chat import ChatResponse, CopilotIntent, IntentDecision, ToolActivity
from ai_data_platform_copilot.domain.metrics import MetricQueryRequest
from ai_data_platform_copilot.ports.chat_provider import ChatProvider


class ChatService:
    def __init__(self, provider: ChatProvider, metadata: MetadataService, metrics: MetricService) -> None:
        self._provider = provider
        self._metadata = metadata
        self._metrics = metrics

    def ask(self, question: str) -> ChatResponse:
        decision = self._provider.classify(question)
        decision = self._ground_metric_decision(question, decision)
        evidence, tool = self._invoke(
            decision.intent,
            decision.search_query,
            decision.metric,
            decision.model,
            decision.group_by,
            decision.year,
        )
        answer = self._provider.compose(question, decision, evidence)
        execution_payload = evidence.get("execution_query")
        execution_query = MetricQueryRequest.model_validate(execution_payload) if execution_payload else None
        return ChatResponse(
            answer=answer,
            intent=decision.intent,
            tool_activity=(ToolActivity(tool=tool, status="completed"),),
            evidence=evidence,
            limitations=("The language model composed prose; deterministic tool evidence is authoritative.",),
            confirmation_required=execution_query is not None,
            execution_query=execution_query,
        )

    def _ground_metric_decision(self, question: str, decision: IntentDecision) -> IntentDecision:
        """Replace model-extracted metric text with a governed identifier when possible."""
        resolved_metric = self._resolve_metric(decision.metric) if decision.metric else None
        if resolved_metric is None:
            resolved_metric = self._resolve_metric(question)
        group_by = self._ground_group_by(question, decision.group_by, resolved_metric)
        year = decision.year or self._extract_year(question)
        intent = decision.intent
        if resolved_metric and (year is not None or group_by) and intent in {
            CopilotIntent.METRIC_DETAILS,
            CopilotIntent.UNSUPPORTED,
        }:
            intent = CopilotIntent.METRIC_COMPILE
        return decision.model_copy(
            update={
                "intent": intent,
                "metric": resolved_metric or decision.metric,
                "group_by": group_by,
                "year": year,
            }
        )

    def _ground_group_by(
        self,
        question: str,
        requested: tuple[str, ...],
        metric_name: str | None,
    ) -> tuple[str, ...]:
        """Resolve user-facing dimension spellings against governed metric dimensions."""
        if metric_name is None:
            return requested
        available = self._metrics.provider.list_metric_dimensions(metric_name)
        normalized_available = {self._normalize(value): value for value in available}
        grounded: list[str] = []
        for value in requested:
            match = normalized_available.get(self._normalize(value))
            if match and match not in grounded:
                grounded.append(match)
        normalized_question = self._normalize(question)
        mentioned = [
            value
            for normalized, value in normalized_available.items()
            if re.search(rf"\b{re.escape(normalized)}\b", normalized_question)
        ]
        if len(mentioned) == 1 and mentioned[0] not in grounded:
            grounded.append(mentioned[0])
        dimension_value_hints = {
            "payment_method": ("credit card", "coupon", "bank transfer", "gift card"),
        }
        for dimension, values in dimension_value_hints.items():
            if dimension not in available or dimension in grounded:
                continue
            if any(re.search(rf"\b{re.escape(value)}\b", normalized_question) for value in values):
                grounded.append(dimension)
        return tuple(grounded)

    def _invoke(
        self,
        intent: CopilotIntent,
        search_query: str | None,
        metric_name: str | None,
        model_name: str | None,
        group_by: tuple[str, ...],
        year: int | None,
    ) -> tuple[dict[str, Any], str]:
        if intent == CopilotIntent.METRIC_LIST:
            return {
                "metrics": [item.model_dump(mode="json") for item in self._metrics.provider.list_metrics()]
            }, "list_metrics"
        resolved_metric = self._resolve_metric(metric_name) if metric_name else None
        if metric_name and resolved_metric is None:
            return {
                "supported": False,
                "requested_metric": metric_name,
                "message": "No governed metric matched the requested name.",
                "available_metrics": [item.name for item in self._metrics.provider.list_metrics()],
            }, "resolve_metric"
        if intent == CopilotIntent.METRIC_DETAILS and resolved_metric:
            return self._metrics.provider.get_metric_details(resolved_metric).model_dump(
                mode="json"
            ), "get_metric_details"
        if intent == CopilotIntent.METRIC_DIMENSIONS and resolved_metric:
            return {
                "metric": resolved_metric,
                "dimensions": self._metrics.provider.list_metric_dimensions(resolved_metric),
            }, "list_metric_dimensions"
        if intent == CopilotIntent.METRIC_COMPILE and resolved_metric:
            query = MetricQueryRequest(
                metric=resolved_metric,
                group_by=group_by,
                start_time=date(year, 1, 1) if year is not None else None,
                end_time=date(year, 12, 31) if year is not None else None,
            )
            compilation = self._metrics.provider.compile_metric_query(query)
            evidence: dict[str, Any] = {
                "metric": self._metrics.provider.get_metric_details(resolved_metric).model_dump(mode="json"),
                "compiled_query": compilation.model_dump(mode="json"),
                "execution_query": query.model_dump(mode="json"),
                "message": "The governed query is compiled and requires explicit confirmation before execution.",
            }
            if year is not None:
                evidence["requested_year"] = year
            return evidence, "compile_metric_query"
        if intent == CopilotIntent.METRIC_IMPACT and model_name:
            return self._metrics.impact(model_name).model_dump(mode="json"), "metric_impact"
        if intent == CopilotIntent.METADATA_SEARCH and search_query:
            return self._metadata.search(search_query).model_dump(mode="json"), "metadata_search"
        return {"supported": False, "message": "That request is outside the configured Phase 3 tools."}, "unsupported"

    def _resolve_metric(self, requested: str) -> str | None:
        """Resolve exact names/labels and an unambiguous token subset without invention."""
        normalized = self._normalize(requested)
        metrics = self._metrics.provider.list_metrics()
        aliases = {
            "aov": "average_order_value",
            "average order value": "average_order_value",
            "revenue": "total_revenue",
            "total order amount": "total_revenue",
            "order amount paid": "total_revenue",
            "order count": "orders",
            "customer count": "customers",
        }
        alias_matches = {
            metric_name
            for alias, metric_name in aliases.items()
            if re.search(rf"\b{re.escape(alias)}\b", normalized)
            and any(metric.name == metric_name for metric in metrics)
        }
        if len(alias_matches) == 1:
            return alias_matches.pop()
        exact = [
            metric
            for metric in metrics
            if normalized in {self._normalize(metric.name), self._normalize(metric.label)}
        ]
        if len(exact) == 1:
            return exact[0].name
        contained = [
            metric
            for metric in metrics
            if re.search(rf"\b{re.escape(self._normalize(metric.name))}\b", normalized)
            or re.search(rf"\b{re.escape(self._normalize(metric.label))}\b", normalized)
        ]
        if len(contained) == 1:
            return contained[0].name
        requested_tokens = set(normalized.split())
        partial = [
            metric
            for metric in metrics
            if requested_tokens and requested_tokens <= set(self._normalize(metric.name).split())
        ]
        if len(partial) == 1:
            return partial[0].name
        token_to_metrics: dict[str, set[str]] = {}
        for metric in metrics:
            for token in self._normalize(metric.name).split():
                token_to_metrics.setdefault(token, set()).add(metric.name)
        fuzzy_metrics: set[str] = set()
        for token in requested_tokens:
            matches = get_close_matches(token, token_to_metrics, n=1, cutoff=0.8)
            if matches:
                fuzzy_metrics.update(token_to_metrics[matches[0]])
        return fuzzy_metrics.pop() if len(fuzzy_metrics) == 1 else None

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())

    @staticmethod
    def _extract_year(value: str) -> int | None:
        years = {int(match) for match in re.findall(r"(?<!\d)(?:19|20|21)\d{2}(?!\d)", value)}
        return years.pop() if len(years) == 1 else None
