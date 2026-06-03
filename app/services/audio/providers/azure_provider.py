"""Provider online: Azure Cognitive Services Speech-to-Text.

Recomendado para clinico ES con custom speech model. EU residency disponible.
Activar instalando `azure-cognitiveservices-speech` y definiendo
AZURE_SPEECH_KEY + AZURE_SPEECH_REGION.
"""
from __future__ import annotations

import logging
import time

from app.core.config import Settings
from app.services.audio.base import Segment, TranscriptionProvider, TranscriptResult


logger = logging.getLogger(__name__)


class AzureSpeechProvider(TranscriptionProvider):
    name = "azure"
    supports_streaming = True
    supports_diarization = True

    def __init__(self, key: str, region: str, endpoint_id: str | None = None) -> None:
        import azure.cognitiveservices.speech as speechsdk  # import diferido

        if not key or not region:
            raise RuntimeError("AZURE_SPEECH_KEY / AZURE_SPEECH_REGION no definidos")
        self._sdk = speechsdk
        self.key = key
        self.region = region
        self.endpoint_id = endpoint_id

    def transcribe(
        self,
        audio_path: str,
        language: str = "es-ES",
        initial_prompt: str | None = None,
        diarize: bool = False,
    ) -> TranscriptResult:
        speechsdk = self._sdk
        config = speechsdk.SpeechConfig(subscription=self.key, region=self.region)
        config.speech_recognition_language = language
        if self.endpoint_id:
            config.endpoint_id = self.endpoint_id

        audio_input = speechsdk.AudioConfig(filename=audio_path)
        recognizer = speechsdk.SpeechRecognizer(speech_config=config, audio_config=audio_input)

        # batch sync simplificado; para diarizacion real usar ConversationTranscriber
        started = time.perf_counter()
        result = recognizer.recognize_once()
        elapsed = time.perf_counter() - started

        text = result.text or ""
        segments: list[Segment] = []
        if text:
            segments.append(Segment(start=0.0, end=elapsed, text=text))

        return TranscriptResult(
            text=text,
            segments=segments,
            language=language,
            duration_s=elapsed,
            rtf=1.0,
            provider=self.name,
            model="azure-default",
        )


def build_azure(settings: Settings) -> TranscriptionProvider:
    return AzureSpeechProvider(
        key=settings.azure_speech_key,
        region=settings.azure_speech_region,
        endpoint_id=settings.azure_speech_endpoint_id,
    )
