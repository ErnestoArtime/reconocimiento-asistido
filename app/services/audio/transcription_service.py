"""Orquestador de transcripcion.

Une preproceso FFmpeg + cache + provider seleccionable + fallback.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from app.core.config import Settings
from app.services.audio import cache, registry
from app.services.audio.audio_preprocess import normalize_audio
from app.services.audio.base import TranscriptResult


logger = logging.getLogger(__name__)


def transcribe_upload(
    raw_bytes: bytes,
    filename: str,
    settings: Settings,
    provider_name: str | None = None,
    language: str | None = None,
    initial_prompt: str | None = None,
    diarize: bool | None = None,
    use_cache: bool = True,
    model: str | None = None,
) -> TranscriptResult:
    """Punto unico de entrada. Devuelve TranscriptResult."""
    chosen_provider = (provider_name or settings.audio_provider).lower()
    chosen_model = model or settings.audio_model
    chosen_language = language or settings.audio_language
    chosen_diarize = settings.audio_diarization if diarize is None else diarize
    chosen_prompt = initial_prompt if initial_prompt is not None else settings.audio_initial_prompt

    with tempfile.TemporaryDirectory(prefix="reco_audio_") as tmp:
        tmp_path = Path(tmp)
        suffix = Path(filename).suffix or ".bin"
        raw_path = tmp_path / f"input{suffix}"
        raw_path.write_bytes(raw_bytes)

        wav_path = tmp_path / "normalized.wav"
        normalize_audio(
            raw_path,
            wav_path,
            sample_rate=16000,
            apply_filters=settings.audio_apply_filters,
        )

        cache_key = ""
        cache_allowed = use_cache and settings.audio_cache_enabled
        if cache_allowed:
            cache_key = cache.hash_file(
                wav_path,
                extra=f"{chosen_provider}|{chosen_model}|{chosen_language}|{chosen_prompt}|diar={chosen_diarize}",
            )
            cached = cache.load(settings.audio_cache_dir, cache_key)
            if cached:
                logger.info("Cache hit %s", cache_key[:12])
                return cached

        result = _transcribe_with_fallback(
            wav_path=str(wav_path),
            provider_name=chosen_provider,
            settings=settings,
            language=chosen_language,
            initial_prompt=chosen_prompt or None,
            diarize=chosen_diarize,
            model=chosen_model,
        )

        if cache_allowed and cache_key:
            cache.save(settings.audio_cache_dir, cache_key, result)
        return result


def _transcribe_with_fallback(
    wav_path: str,
    provider_name: str,
    settings: Settings,
    language: str,
    initial_prompt: str | None,
    diarize: bool,
    model: str | None = None,
) -> TranscriptResult:
    try:
        provider = registry.get_provider(provider_name, model)
        return provider.transcribe(
            audio_path=wav_path,
            language=language,
            initial_prompt=initial_prompt,
            diarize=diarize,
        )
    except Exception as exc:  # noqa: BLE001
        fallback = settings.audio_fallback_provider
        if fallback and fallback != provider_name:
            logger.warning(
                "Provider '%s' fallo (%s). Intentando fallback '%s'.",
                provider_name,
                exc,
                fallback,
            )
            provider = registry.get_provider(fallback)
            return provider.transcribe(
                audio_path=wav_path,
                language=language,
                initial_prompt=initial_prompt,
                diarize=diarize,
            )
        raise
