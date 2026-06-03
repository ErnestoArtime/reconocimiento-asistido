"""Servicio de transcripcion de audio.

Patron pluggable: TranscriptionProvider abstracto, multiples backends locales
y online seleccionables por configuracion. Mismo patron que llm_provider.
"""
from app.services.audio.base import (
    PartialTranscript,
    Segment,
    TranscriptionProvider,
    TranscriptResult,
)
from app.services.audio.registry import (
    available_providers,
    get_provider,
)

__all__ = [
    "PartialTranscript",
    "Segment",
    "TranscriptionProvider",
    "TranscriptResult",
    "available_providers",
    "get_provider",
]
