"""Port for optional language-only orchestration."""

from __future__ import annotations

from typing import Any, Protocol

from ai_data_platform_copilot.domain.chat import IntentDecision


class ChatProvider(Protocol):
    def classify(self, question: str) -> IntentDecision: ...
    def compose(self, question: str, decision: IntentDecision, evidence: dict[str, Any]) -> str: ...
