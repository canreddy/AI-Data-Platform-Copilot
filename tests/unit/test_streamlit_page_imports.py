"""Regression tests for Streamlit's page-directory import semantics."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGES_DIR = ROOT / "apps" / "ui" / "app_pages"


def test_pages_run_without_repository_root_on_python_path() -> None:
    """Streamlit page scripts must import only installed shared packages."""
    environment = os.environ.copy()
    environment["COPILOT_API_URL"] = "http://127.0.0.1:1"
    for page in ("metadata.py", "lineage.py", "sql_review.py", "metrics.py", "copilot.py"):
        result = subprocess.run(
            [sys.executable, str(PAGES_DIR / page)],
            cwd=PAGES_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert "ModuleNotFoundError" not in result.stderr
