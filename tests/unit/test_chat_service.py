from pathlib import Path
from typing import Any
from unittest.mock import Mock

from ai_data_platform_copilot.adapters.dbt.semantic import ArtifactSemanticProvider
from ai_data_platform_copilot.application.chat_service import ChatService
from ai_data_platform_copilot.application.metric_service import MetricService
from ai_data_platform_copilot.application.services import MetadataService
from ai_data_platform_copilot.domain.chat import CopilotIntent, IntentDecision
from ai_data_platform_copilot.domain.metrics import MetricQueryCompilation, MetricQueryRequest

ROOT = Path(__file__).resolve().parents[2]


class RevenueQuestionProvider:
    def classify(self, question: str) -> IntentDecision:
        return IntentDecision(intent=CopilotIntent.METRIC_COMPILE, metric="revinue", year=2018)

    def compose(self, question: str, decision: IntentDecision, evidence: dict[str, Any]) -> str:
        return str(evidence["message"])


class UnreliableAverageOrderValueProvider:
    def __init__(self, metric: str | None, intent: CopilotIntent = CopilotIntent.METRIC_COMPILE) -> None:
        self._metric = metric
        self._intent = intent

    def classify(self, question: str) -> IntentDecision:
        return IntentDecision(intent=self._intent, metric=self._metric)

    def compose(self, question: str, decision: IntentDecision, evidence: dict[str, Any]) -> str:
        return str(evidence["message"])


class OrderStatusProvider:
    def classify(self, question: str) -> IntentDecision:
        return IntentDecision(
            intent=CopilotIntent.METRIC_COMPILE,
            metric="order count",
            group_by=("order_status",),
        )

    def compose(self, question: str, decision: IntentDecision, evidence: dict[str, Any]) -> str:
        return str(evidence["message"])


class UnsupportedProvider:
    def classify(self, question: str) -> IntentDecision:
        return IntentDecision(intent=CopilotIntent.UNSUPPORTED)

    def compose(self, question: str, decision: IntentDecision, evidence: dict[str, Any]) -> str:
        return str(evidence["message"])


class CompilingArtifactProvider(ArtifactSemanticProvider):
    def compile_metric_query(self, request: MetricQueryRequest) -> MetricQueryCompilation:
        validation = self.validate_metric_query(request)
        return MetricQueryCompilation(
            request=request,
            validation=validation,
            sql="select 123 as total_revenue",
            evidence=validation.evidence,
        )


def test_metric_alias_and_year_request_return_evidence_instead_of_not_found() -> None:
    semantic_provider = CompilingArtifactProvider(ROOT / "demo" / "jaffle_shop" / "target")
    metadata = Mock(spec=MetadataService)
    service = ChatService(RevenueQuestionProvider(), metadata, MetricService(semantic_provider))

    response = service.ask("What is the revenue for 2018?")

    assert response.intent == CopilotIntent.METRIC_COMPILE
    assert response.evidence["metric"]["name"] == "total_revenue"
    assert response.evidence["requested_year"] == 2018
    assert response.confirmation_required is True
    assert response.execution_query is not None
    assert response.execution_query.start_time is not None
    assert response.execution_query.end_time is not None
    assert response.execution_query.start_time.isoformat() == "2018-01-01"
    assert response.execution_query.end_time.isoformat() == "2018-12-31"
    assert "confirmation" in response.answer


def test_average_order_value_is_grounded_from_question_when_model_omits_metric_and_year() -> None:
    semantic_provider = CompilingArtifactProvider(ROOT / "demo" / "jaffle_shop" / "target")
    metadata = Mock(spec=MetadataService)
    service = ChatService(
        UnreliableAverageOrderValueProvider(None),
        metadata,
        MetricService(semantic_provider),
    )

    response = service.ask("What is average_order_value for 2018?")

    assert response.intent == CopilotIntent.METRIC_COMPILE
    assert response.evidence["metric"]["name"] == "average_order_value"
    assert response.evidence["requested_year"] == 2018
    assert response.execution_query is not None
    assert response.execution_query.metric == "average_order_value"


def test_aov_alias_overrides_unreliable_model_extraction() -> None:
    semantic_provider = CompilingArtifactProvider(ROOT / "demo" / "jaffle_shop" / "target")
    metadata = Mock(spec=MetadataService)
    service = ChatService(
        UnreliableAverageOrderValueProvider("order value", CopilotIntent.METRIC_DETAILS),
        metadata,
        MetricService(semantic_provider),
    )

    response = service.ask("What was AOV in 2018?")

    assert response.intent == CopilotIntent.METRIC_COMPILE
    assert response.evidence["metric"]["name"] == "average_order_value"
    assert response.confirmation_required is True


def test_grouped_metric_without_year_still_requires_execution_confirmation() -> None:
    semantic_provider = CompilingArtifactProvider(ROOT / "demo" / "jaffle_shop" / "target")
    metadata = Mock(spec=MetadataService)
    service = ChatService(OrderStatusProvider(), metadata, MetricService(semantic_provider))

    response = service.ask("What is the order count based on order status?")

    assert response.evidence["metric"]["name"] == "orders"
    assert response.confirmation_required is True
    assert response.execution_query is not None
    assert response.execution_query.group_by == ("order_status",)


def test_missing_metric_time_wording_is_grounded_to_governed_year_query() -> None:
    semantic_provider = CompilingArtifactProvider(ROOT / "demo" / "jaffle_shop" / "target")
    metadata = Mock(spec=MetadataService)
    service = ChatService(UnsupportedProvider(), metadata, MetricService(semantic_provider))

    response = service.ask("Why are we missing metric_time_year for 38 customers?")

    assert response.intent == CopilotIntent.METRIC_COMPILE
    assert response.confirmation_required is True
    assert response.execution_query is not None
    assert response.execution_query.metric == "customers"
    assert response.execution_query.group_by == ("metric_time__year",)
    assert response.execution_query.start_time is None


def test_total_order_amount_by_credit_card_maps_to_revenue_by_payment_method() -> None:
    semantic_provider = CompilingArtifactProvider(ROOT / "demo" / "jaffle_shop" / "target")
    metadata = Mock(spec=MetadataService)
    service = ChatService(UnsupportedProvider(), metadata, MetricService(semantic_provider))

    response = service.ask("What is the total order amount paid through credit_card?")

    assert response.intent == CopilotIntent.METRIC_COMPILE
    assert response.confirmation_required is True
    assert response.execution_query is not None
    assert response.execution_query.metric == "total_revenue"
    assert response.execution_query.group_by == ("payment_method",)
