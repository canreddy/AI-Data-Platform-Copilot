"""Structured application errors."""


class CopilotError(Exception):
    """Base exception with a stable machine-readable code."""

    code = "copilot_error"


class ArtifactError(CopilotError):
    """Artifact is missing, invalid, or unsupported."""

    code = "artifact_error"


class SnapshotNotFoundError(CopilotError):
    """No requested or active metadata snapshot exists."""

    code = "snapshot_not_found"


class ResourceNotFoundError(CopilotError):
    """A resource selector could not be resolved."""

    code = "resource_not_found"


class AmbiguousResourceError(CopilotError):
    """A resource name resolved to more than one unique dbt resource."""

    code = "ambiguous_resource"


class MetricNotFoundError(CopilotError):
    """Requested governed metric does not exist in the active semantic manifest."""

    code = "metric_not_found"


class SemanticModelNotFoundError(CopilotError):
    """Requested semantic model does not exist in the active manifest."""

    code = "semantic_model_not_found"


class MetricFlowCapabilityError(CopilotError):
    """MetricFlow is unavailable or rejected a compile-only request."""

    code = "metricflow_unavailable"


class MetricExecutionError(CopilotError):
    """Narrow demo metric execution was rejected or failed safely."""

    code = "metric_execution_error"
