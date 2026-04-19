"""Vercel ASGI entrypoint for the FastAPI application."""

from __future__ import annotations

from api.app import create_app


class _LazyApp:
    title = "Job Cost Tool API"

    def __init__(self) -> None:
        self._app = None

    def _resolve(self):
        if self._app is None:
            self._app = create_app()
        return self._app

    async def __call__(self, scope, receive, send):
        await self._resolve()(scope, receive, send)

    def __getattr__(self, name: str):
        return getattr(self._resolve(), name)


app = _LazyApp()
