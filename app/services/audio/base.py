"""Interfaz comun para proveedores de transcripcion (local u online).

Cualquier nuevo backend (faster-whisper, WhisperX, Azure, OpenAI, Deepgram, ...)
debe heredar de TranscriptionProvider y devolver TranscriptResult.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterable, AsyncIterator


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker: str | None = None
    confidence: float | None = None


@dataclass
class TranscriptResult:
    text: str
    segments: list[Segment] = field(default_factory=list)
    language: str = "es"
    duration_s: float = 0.0
    rtf: float = 0.0  # processing_time / audio_duration
    provider: str = ""
    model: str = ""

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "language": self.language,
            "duration_s": round(self.duration_s, 3),
            "rtf": round(self.rtf, 3),
            "provider": self.provider,
            "model": self.model,
            "segments": [
                {
                    "start": round(s.start, 3),
                    "end": round(s.end, 3),
                    "text": s.text,
                    "speaker": s.speaker,
                    "confidence": s.confidence,
                }
                for s in self.segments
            ],
        }


@dataclass
class PartialTranscript:
    text: str
    is_final: bool
    start: float
    end: float


class TranscriptionProvider(ABC):
    """Contrato comun para todos los backends de transcripcion."""

    name: str = "abstract"
    supports_streaming: bool = False
    supports_diarization: bool = False
    supports_model_selection: bool = False

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        language: str = "es",
        initial_prompt: str | None = None,
        diarize: bool = False,
    ) -> TranscriptResult:
        """Transcribe un archivo de audio ya normalizado (WAV 16k mono)."""

    async def stream(
        self,
        chunks: AsyncIterable[bytes],
        language: str = "es",
        initial_prompt: str | None = None,
    ) -> AsyncIterator[PartialTranscript]:
        """Streaming opcional. Default: NotImplemented."""
        raise NotImplementedError(f"{self.name} no soporta streaming")
        # pragma para tipado
        yield  # type: ignore[unreachable]

    def capabilities(self) -> dict:
        return {
            "name": self.name,
            "supports_streaming": self.supports_streaming,
            "supports_diarization": self.supports_diarization,
            "supports_model_selection": self.supports_model_selection,
            "model": getattr(self, "model_size", None) or getattr(self, "model", None),
        }
