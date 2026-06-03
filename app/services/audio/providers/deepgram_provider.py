"""Provider online: Deepgram nova-2-medical.

Streaming bajo latencia, modelo medico. Requiere DEEPGRAM_API_KEY.
"""
from __future__ import annotations

import logging
import time

from app.core.config import Settings
from app.services.audio.base import Segment, TranscriptionProvider, TranscriptResult


logger = logging.getLogger(__name__)


class DeepgramProvider(TranscriptionProvider):
    name = "deepgram"
    supports_streaming = True
    supports_diarization = True

    def __init__(self, api_key: str, model: str = "nova-2-medical") -> None:
        from deepgram import DeepgramClient  # import diferido

        if not api_key:
            raise RuntimeError("DEEPGRAM_API_KEY no definida")
        self._client = DeepgramClient(api_key)
        self.model = model

    def transcribe(
        self,
        audio_path: str,
        language: str = "es",
        initial_prompt: str | None = None,
        diarize: bool = False,
    ) -> TranscriptResult:
        from deepgram import PrerecordedOptions, FileSource  # type: ignore

        with open(audio_path, "rb") as fh:
            buffer = fh.read()
        payload: FileSource = {"buffer": buffer}
        options = PrerecordedOptions(
            model=self.model,
            language=language,
            diarize=diarize,
            smart_format=True,
            punctuate=True,
        )

        started = time.perf_counter()
        response = self._client.listen.rest.v("1").transcribe_file(payload, options)
        elapsed = time.perf_counter() - started

        results = response.get("results", {}) if isinstance(response, dict) else {}
        channels = results.get("channels", [])
        alt = channels[0].get("alternatives", [{}])[0] if channels else {}
        text = alt.get("transcript", "")
        words = alt.get("words", [])
        segments = [
            Segment(
                start=float(w.get("start", 0.0)),
                end=float(w.get("end", 0.0)),
                text=str(w.get("punctuated_word", w.get("word", ""))),
                speaker=str(w.get("speaker")) if "speaker" in w else None,
                confidence=w.get("confidence"),
            )
            for w in words
        ]
        duration = float(results.get("metadata", {}).get("duration", elapsed))
        rtf = elapsed / duration if duration > 0 else 0.0
        return TranscriptResult(
            text=text,
            segments=segments,
            language=language,
            duration_s=duration,
            rtf=rtf,
            provider=self.name,
            model=self.model,
        )


def build_deepgram(settings: Settings) -> TranscriptionProvider:
    return DeepgramProvider(
        api_key=settings.deepgram_api_key,
        model=settings.deepgram_model,
    )
