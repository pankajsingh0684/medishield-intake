"""ASGI entry point for local development and deployment."""

from apps.api.factory import create_app

app = create_app()
