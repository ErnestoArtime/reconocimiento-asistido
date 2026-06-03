"""Provider online: OpenAI Whisper API / gpt-4o-transcribe.

Activar instalando `openai` y definiendo OPENAI_API_KEY.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from app.core.config import Settings
from app.services.audio.base import Segment, TranscriptionProvider, TranscriptResult


logger = logging.getLogger(__name__)


class OpenAIProvider(TranscriptionProvider):
    name = "openai"
    supports_streaming = False
    supports_diarization = False

    def __init__(self, api_key: str, model: str = "whisper-1") -> None:
        from openai import OpenAI  # import diferido

        if not api_key:
            raise RuntimeError("OPENAI_API_KEY no definida")
        self._client = OpenAI(api_key=api_key)
        self.model = model

    def transcribe(
        self,
        audio_path: str,
        language: str = "es",
        initial_prompt: str | None = None,
        diarize: bool = False,
    ) -> TranscriptResult:
        started = time.perf_counter()
        with open(audio_path, "rb") as fh:
            response = self._client.audio.transcriptions.create(
                model=self.model,
                file=fh,
                language=language,
                prompt=initial_prompt or "",
                response_format="verbose_json",
            )
        elapsed = time.perf_counter() - started

        text = getattr(response, "text", "") or ""
        duration = float(getattr(response, "duration", 0.0) or 0.0)
        raw_segments = getattr(response, "segments", []) or []
        segments = [
            Segment(
                start=float(s.get("start", 0.0)),
                end=float(s.get("end", 0.0)),
                text=str(s.get("text", "")).strip(),
                confidence=s.get("avg_logprob"),
            )
            for s in raw_segments
        ]
        rtf = elapsed / duration if duration > 0 else 0.0
        return TranscriptResult(
            text=text.strip(),
            segments=segments,
            language=language,
            duration_s=duration,
            rtf=rtf,
            provider=self.name,
            model=self.model,
        )


def build_openai(settings: Settings) -> TranscriptionProvider:
    return OpenAIProvider(
        api_key=settings.openai_api_key,
        model=settings.openai_audio_model,
    )
