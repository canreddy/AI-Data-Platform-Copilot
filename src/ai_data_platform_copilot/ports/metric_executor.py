"""Port for narrowly scoped governed metric execution."""

from __future__ import annotations

from typing import Protocol

from ai_data_platform_copilot.domain.metrics import MetricExecutionResult, MetricQueryCompilation


class MetricExecutor(Protocol):
    def execute(self, compilation: MetricQueryCompilation) -> MetricExecutionResult: ...
