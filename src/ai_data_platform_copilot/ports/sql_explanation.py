"""Optional SQL explanation provider boundary."""

from typing import Protocol

from ai_data_platform_copilot.domain.sql_review import SQLExplanation, SQLReviewResponse


class SQLExplanationProvider(Protocol):
    """Compose prose from an already-complete deterministic review."""

    def explain(self, review: SQLReviewResponse) -> SQLExplanation: ...
