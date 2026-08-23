"""Small typed HTTP client for deterministic explorer pages."""

from __future__ import annotations

import os
from typing import Any

import httpx

API_URL = os.getenv("COPILOT_API_URL", "http://localhost:8000")


def get_json(path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch JSON from the local API with a bounded timeout."""
    response = httpx.get(f"{API_URL}{path}", params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("Copilot API returned a non-object response")
    return payload


def get_list(path: str, *, params: dict[str, Any] | None = None) -> list[Any]:
    """Fetch a JSON array from the local API with a bounded timeout."""
    response = httpx.get(f"{API_URL}{path}", params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise TypeError("Copilot API returned a non-array response")
    return payload


def post_json(path: str, *, payload: dict[str, Any]) -> dict[str, Any]:
    """Post JSON to the local API with a bounded timeout."""
    response = httpx.post(f"{API_URL}{path}", json=payload, timeout=10)
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise TypeError("Copilot API returned a non-object response")
    return value
