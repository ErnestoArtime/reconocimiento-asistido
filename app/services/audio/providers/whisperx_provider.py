"""Provider local con diarizacion: WhisperX + pyannote.

Pesado. Requiere torch + whisperx + pyannote.audio y token HF.
Solo carga si se selecciona AUDIO_PROVIDER=whisperx.
"""
from __future__ import annotations

import logging
import os
import time
from inspect import signature

from app.core.config import Settings
from app.services.audio.base import Segment, TranscriptionProvider, TranscriptResult


logger = logging.getLogger(__name__)


class WhisperXProvider(TranscriptionProvider):
    name = "whisperx"
    supports_streaming = False
    supports_diarization = True

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cuda",
        compute_type: str = "float16",
        hf_token: str | None = None,
        diarization_model: str | None = None,
        offline_mode: bool = False,
        cache_dir: str | None = None,
        batch_size: int = 16,
    ) -> None:
        if cache_dir:
            os.environ.setdefault("HF_HOME", cache_dir)
            os.environ.setdefault("HUGGINGFACE_HUB_CACHE", cache_dir)
        if offline_mode:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        import whisperx  # type: ignore

        self._whisperx = whisperx
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.hf_token = hf_token
        self.diarization_model = diarization_model
        self.batch_size = batch_size

        logger.info("Cargando WhisperX %s device=%s", model_size, device)
        self._model = whisperx.load_model(model_size, device, compute_type=compute_type)
        self._align_cache: dict[str, tuple] = {}
        self._diarizer = None

    def _get_aligner(self, language: str):
        if language in self._align_cache:
            return self._align_cache[language]
        model_a, metadata = self._whisperx.load_align_model(
            language_code=language, device=self.device
        )
        self._align_cache[language] = (model_a, metadata)
        return model_a, metadata

    def _get_diarizer(self):
        if self._diarizer is not None:
            return self._diarizer
        if not self.hf_token and not self.diarization_model:
            raise RuntimeError(
                "HF_TOKEN o WHISPERX_DIARIZATION_MODEL local requerido para diarizacion"
            )
        pipeline_cls = self._whisperx.DiarizationPipeline
        params = signature(pipeline_cls).parameters
        kwargs = {"device": self.device}
        if self.hf_token and "use_auth_token" in params:
            kwargs["use_auth_token"] = self.hf_token
        if self.diarization_model:
            if "model_name" in params:
                kwargs["model_name"] = self.diarization_model
            elif "model" in params:
                kwargs["model"] = self.diarization_model
            else:
                logger.warning(
                    "WhisperX DiarizationPipeline no expone parametro para modelo local; "
                    "se intentara pipeline por defecto"
                )
        self._diarizer = pipeline_cls(**kwargs)
        return self._diarizer

    def transcribe(
        self,
        audio_path: str,
        language: str = "es",
        initial_prompt: str | None = None,
        diarize: bool = False,
    ) -> TranscriptResult:
        whisperx = self._whisperx
        started = time.perf_counter()

        audio = whisperx.load_audio(audio_path)
        asr_options = {"initial_prompt": initial_prompt} if initial_prompt else None
        tr = self._model.transcribe(
            audio,
            batch_size=self.batch_size,
            language=language,
            **({"options": asr_options} if asr_options else {}),
        )

        model_a, metadata = self._get_aligner(language)
        aligned = whisperx.align(
            tr["segments"],
            model_a,
            metadata,
            audio,
            self.device,
            return_char_alignments=False,
        )
        segments_raw = aligned.get("segments", tr["segments"])

        if diarize:
            diarizer = self._get_diarizer()
            diar = diarizer(audio)
            assigned = whisperx.assign_word_speakers(diar, {"segments": segments_raw})
            segments_raw = assigned.get("segments", segments_raw)

        segments: list[Segment] = []
        text_parts: list[str] = []
        for seg in segments_raw:
            segments.append(
                Segment(
                    start=float(seg.get("start", 0.0)),
                    end=float(seg.get("end", 0.0)),
                    text=str(seg.get("text", "")).strip(),
                    speaker=seg.get("speaker"),
                )
            )
            text_parts.append(seg.get("text", ""))

        elapsed = time.perf_counter() - started
        duration = float(segments[-1].end) if segments else 0.0
        rtf = elapsed / duration if duration > 0 else 0.0

        return TranscriptResult(
            text=" ".join(part.strip() for part in text_parts).strip(),
            segments=map_speakers_to_roles(segments),
            language=language,
            duration_s=duration,
            rtf=rtf,
            provider=self.name,
            model=self.model_size,
        )


_QUESTION_MARKERS = ("?", "cuanto", "cuando", "donde", "como", "tiene", "padece", "fuma")


def map_speakers_to_roles(segments: list[Segment]) -> list[Segment]:
    """Mapea SPEAKER_00/01 -> medico/paciente heuristicamente.

    Quien hace mas preguntas = medico. Quien responde = paciente.
    """
    if not segments:
        return segments
    counts: dict[str, int] = {}
    for seg in segments:
        if not seg.speaker:
            continue
        text = (seg.text or "").lower()
        if any(marker in text for marker in _QUESTION_MARKERS):
            counts[seg.speaker] = counts.get(seg.speaker, 0) + 1

    if not counts:
        return segments

    medico = max(counts, key=counts.get)
    role_map: dict[str, str] = {}
    role_map[medico] = "medico"
    for seg in segments:
        if seg.speaker and seg.speaker not in role_map:
            role_map[seg.speaker] = "paciente"

    return [
        Segment(
            start=s.start,
            end=s.end,
            text=s.text,
            speaker=role_map.get(s.speaker, s.speaker) if s.speaker else None,
            confidence=s.confidence,
        )
        for s in segments
    ]


def build_whisperx(settings: Settings) -> TranscriptionProvider:
    return WhisperXProvider(
        model_size=settings.audio_model,
        device=settings.audio_device if settings.audio_device != "auto" else "cuda",
        compute_type=settings.audio_compute_type if settings.audio_compute_type != "auto" else "float16",
        hf_token=settings.whisperx_hf_token or None,
        diarization_model=settings.whisperx_diarization_model or None,
        offline_mode=settings.audio_offline_mode,
        cache_dir=settings.audio_model_cache_dir or None,
    )
