"""Factory de proveedores de transcripcion.

Crea instancias por nombre. Mantiene instancias cacheadas (los modelos
locales son caros de cargar). Permite alternar provider en runtime sin
recargar la app.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Callable

from app.core.config import Settings, get_settings
from app.services.audio.base import TranscriptionProvider


logger = logging.getLogger(__name__)


# Registro de constructores: nombre -> factory(settings) -> provider
_BUILDERS: dict[str, Callable[[Settings], TranscriptionProvider]] = {}


def register(name: str, builder: Callable[[Settings], TranscriptionProvider]) -> None:
    _BUILDERS[name] = builder


def available_providers() -> list[str]:
    return sorted(_BUILDERS.keys())


def _shadow_with_model(settings: Settings, audio_model: str) -> object:
    """Copia superficial de settings con audio_model sobreescrito."""
    class _ShadowSettings:
        pass

    shadow = _ShadowSettings()
    for attr in dir(settings):
        if attr.startswith("_"):
            continue
        try:
            setattr(shadow, attr, getattr(settings, attr))
        except Exception:  # noqa: BLE001
            pass
    shadow.audio_model = audio_model
    return shadow


@lru_cache(maxsize=8)
def get_provider(
    name: str | None = None, model: str | None = None
) -> TranscriptionProvider:
    """Devuelve provider cacheado por (name, model).

    `model` permite seleccionar tamano (medium/large-v3) en runtime sin recargar
    el resto. Cada (provider, modelo) se carga una sola vez.
    """
    settings = get_settings()
    chosen = (name or settings.audio_provider).lower()
    if chosen not in _BUILDERS:
        raise ValueError(
            f"Provider de audio desconocido: '{chosen}'. "
            f"Disponibles: {available_providers()}"
        )
    build_settings = settings
    if model and model != settings.audio_model:
        build_settings = _shadow_with_model(settings, model)
    logger.info("Cargando provider de audio: %s model=%s", chosen, model or settings.audio_model)
    return _BUILDERS[chosen](build_settings)


@lru_cache(maxsize=4)
def get_streaming_provider(name: str | None = None) -> TranscriptionProvider:
    """Provider dedicado a streaming. Usa AUDIO_STREAM_MODEL/AUDIO_STREAM_PROVIDER
    si estan definidos; sino reusa el batch.
    """
    settings = get_settings()
    chosen = (name or settings.audio_stream_provider or settings.audio_provider).lower()
    if chosen not in _BUILDERS:
        raise ValueError(
            f"Provider de streaming desconocido: '{chosen}'. "
            f"Disponibles: {available_providers()}"
        )
    if not settings.audio_stream_model:
        # No hay override de modelo: usa el provider batch ya cacheado
        return get_provider(chosen)

    # Hay modelo distinto: hay que construir provider especifico con shadow settings
    class _StreamSettings:
        pass

    shadow = _StreamSettings()
    for attr in dir(settings):
        if attr.startswith("_"):
            continue
        try:
            setattr(shadow, attr, getattr(settings, attr))
        except Exception:
            pass
    shadow.audio_model = settings.audio_stream_model
    logger.info(
        "Cargando provider streaming: %s model=%s", chosen, settings.audio_stream_model
    )
    return _BUILDERS[chosen](shadow)


def _register_default_providers() -> None:
    """Registra los providers conocidos. Cada import puede fallar si la dep no
    esta instalada; se omite silenciosamente."""

    try:
        from app.services.audio.providers.faster_whisper_provider import (
            build_faster_whisper,
        )

        register("faster_whisper", build_faster_whisper)
    except Exception as exc:  # noqa: BLE001
        logger.warning("faster_whisper no disponible: %s", exc)

    # Hooks para sprints siguientes (no rompen si las deps no estan):
    try:
        from app.services.audio.providers.whisperx_provider import build_whisperx

        register("whisperx", build_whisperx)
    except Exception as exc:  # noqa: BLE001
        logger.debug("whisperx no disponible: %s", exc)

    try:
        from app.services.audio.providers.openai_provider import build_openai

        register("openai", build_openai)
    except Exception:
        pass

    try:
        from app.services.audio.providers.azure_provider import build_azure

        register("azure", build_azure)
    except Exception:
        pass

    try:
        from app.services.audio.providers.deepgram_provider import build_deepgram

        register("deepgram", build_deepgram)
    except Exception:
        pass


_register_default_providers()
