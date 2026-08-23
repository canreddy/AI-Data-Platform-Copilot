"""Environment-backed application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    """Runtime paths and behavior toggles."""

    metadata_database_path: Path
    artifact_directory: Path
    dbt_project_directory: Path = REPOSITORY_ROOT / "demo" / "jaffle_shop"
    metricflow_executable: Path = REPOSITORY_ROOT / ".venv" / "bin" / "mf"
    metric_execution_enabled: bool = True
    auto_ingest: bool = True
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4-mini"

    @classmethod
    def from_environment(cls) -> Settings:
        # Parse local development configuration without shell execution. Exported
        # environment variables retain precedence and secret values are never logged.
        load_dotenv(REPOSITORY_ROOT / ".env", override=False)
        return cls(
            metadata_database_path=Path(
                os.getenv("COPILOT_METADATA_DB", str(REPOSITORY_ROOT / "data" / "metadata.sqlite3"))
            ),
            artifact_directory=Path(
                os.getenv("COPILOT_ARTIFACT_DIR", str(REPOSITORY_ROOT / "demo" / "jaffle_shop" / "target"))
            ),
            dbt_project_directory=Path(
                os.getenv("COPILOT_DBT_PROJECT_DIR", str(REPOSITORY_ROOT / "demo" / "jaffle_shop"))
            ),
            metricflow_executable=Path(
                os.getenv("COPILOT_METRICFLOW_EXECUTABLE", str(REPOSITORY_ROOT / ".venv" / "bin" / "mf"))
            ),
            metric_execution_enabled=os.getenv("COPILOT_METRIC_EXECUTION_ENABLED", "true").casefold()
            in {"1", "true", "yes"},
            auto_ingest=os.getenv("COPILOT_AUTO_INGEST", "true").casefold() in {"1", "true", "yes"},
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
        )
