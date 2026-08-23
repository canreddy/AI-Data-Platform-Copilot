"""ASGI entry point."""

from ai_data_platform_copilot.api.app import create_app

app = create_app()

__all__ = ["app"]
