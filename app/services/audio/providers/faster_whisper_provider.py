"""Provider local basado en faster-whisper (CTranslate2).

Default del proyecto: privado, sin internet, buena precision ES.
"""
from __future__ import annotations

import logging
import time

from app.core.config import Settings
from app.services.audio.base import Segment, TranscriptionProvider, TranscriptResult


logger = logging.getLogger(__name__)


class FasterWhisperProvider(TranscriptionProvider):
    name = "faster_whisper"
    supports_streaming = False  # Streaming real llega en sprint 4 via VAD + chunks
    supports_diarization = False
    supports_model_selection = True

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "auto",
        compute_type: str = "auto",
        beam_size: int = 5,
        vad_filter: bool = True,
        cpu_threads: int = 0,
    ) -> None:
        from faster_whisper import WhisperModel  # import diferido

        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.vad_filter = vad_filter

        logger.info(
            "Cargando faster-whisper model=%s device=%s compute=%s",
            model_size,
            device,
            compute_type,
        )
        self._model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
        )

    def transcribe(
        self,
        audio_path: str,
        language: str = "es",
        initial_prompt: str | None = None,
        diarize: bool = False,
    ) -> TranscriptResult:
        if diarize:
            logger.warning("faster_whisper no diariza; usa whisperx en sprint 5")

        started = time.perf_counter()
        segments_iter, info = self._model.transcribe(
            audio_path,
            language=language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            initial_prompt=initial_prompt,
            word_timestamps=False,
            condition_on_previous_text=True,
        )
        segments: list[Segment] = []
        text_parts: list[str] = []
        for seg in segments_iter:
            segments.append(
                Segment(
                    start=float(seg.start or 0.0),
                    end=float(seg.end or 0.0),
                    text=seg.text.strip(),
                    confidence=getattr(seg, "avg_logprob", None),
                )
            )
            text_parts.append(seg.text)

        elapsed = time.perf_counter() - started
        duration = float(getattr(info, "duration", 0.0) or 0.0)
        rtf = elapsed / duration if duration > 0 else 0.0

        return TranscriptResult(
            text=" ".join(part.strip() for part in text_parts).strip(),
            segments=segments,
            language=getattr(info, "language", language) or language,
            duration_s=duration,
            rtf=rtf,
            provider=self.name,
            model=self.model_size,
        )


def build_faster_whisper(settings: Settings) -> TranscriptionProvider:
    return FasterWhisperProvider(
        model_size=settings.audio_model,
        device=settings.audio_device,
        compute_type=settings.audio_compute_type,
        beam_size=settings.audio_beam_size,
        vad_filter=settings.audio_vad_filter,
        cpu_threads=settings.audio_cpu_threads,
    )
