from __future__ import annotations

from fastapi import HTTPException

from app.core.config import Settings


ONLINE_IA_PROVIDERS = {"cloudflare", "both_cloudflare"}
ONLINE_AUDIO_PROVIDERS = {"openai", "azure", "deepgram"}


def enforce_ia_provider_allowed(provider: str, settings: Settings) -> None:
    if settings.local_only and provider in ONLINE_IA_PROVIDERS:
        raise HTTPException(
            status_code=403,
            detail=f"IA provider '{provider}' bloqueado por DEPLOYMENT_PROFILE={settings.deployment_profile}",
        )


def enforce_audio_provider_allowed(provider: str | None, settings: Settings) -> None:
    chosen = (provider or settings.audio_provider).strip().lower()
    if settings.local_only and chosen in ONLINE_AUDIO_PROVIDERS:
        raise HTTPException(
            status_code=403,
            detail=f"Audio provider '{chosen}' bloqueado por DEPLOYMENT_PROFILE={settings.deployment_profile}",
        )
