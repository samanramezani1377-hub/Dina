"""Cloudflare Workers entrypoint for the existing Dina FastAPI app."""

from workers import asgi
from backend.src.main import app

# Cloudflare's ASGI adapter serves the same FastAPI application used by Uvicorn.
Default = asgi.entrypoint(app)
