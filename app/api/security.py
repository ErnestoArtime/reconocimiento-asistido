from __future__ import annotations

from fastapi import Header, HTTPException

from app.core.config import Settings


def enforce_internal_api_key(
    settings: Settings,
    provided_key: str | None,
) -> None:
    if settings.deployment_profile == "demo":
        return
    if not settings.internal_api_key:
        raise HTTPException(
            status_code=503,
            detail="INTERNAL_API_KEY requerido para perfiles no demo",
        )
    if provided_key != settings.internal_api_key:
        raise HTTPException(status_code=401, detail="API key interna invalida")


def internal_api_key_header(
    x_internal_api_key: str | None = Header(default=None, alias="X-Internal-API-Key"),
) -> str | None:
    return x_internal_api_key
