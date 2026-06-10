from __future__ import annotations

import re

from app.models.extraction_contract import SpeakerRole, SuggestionV1, TranscriptionMetaV1
from app.models.legacy_adapter import _coerce_speaker
from app.services.audio.base import Segment, TranscriptResult
from app.services.audio.evidence_alignment import align_evidence_to_segments


# Hablante cuyo discurso es la fuente clinica por modulo cuando el rol esta
# identificado explicitamente. Los clusters SPEAKER_00/01 no se consideran rol.
EXPECTED_SPEAKER_BY_MODULE = {"history": "paciente", "exam": "medico"}


def _strip_turn_prefix(text: str) -> str:
    return re.sub(r"^\s*\[[^\]]+\]\s*", "", text or "").strip()


def _turn_prefix(segment: Segment) -> str:
    cluster = (segment.speaker or "NO_SPEAKER").strip() or "NO_SPEAKER"
    role = _coerce_speaker(segment.speaker) or "unknown"
    return f"[{cluster}|role={role}]"


def extraction_text_for_module(transcription: TranscriptResult, module: str) -> str:
    """Texto a extraer preservando contexto conversacional.

    Si hay segmentos con speaker, devuelve todos los turnos con prefijo de
    hablante. Esto permite que history use la pregunta del medico como contexto
    sin convertirla en evidencia, y que exam acepte hallazgos dictados por el
    medico. Sin diarizacion, devuelve el transcript plano.
    """
    segments = list(transcription.segments)
    if not any(s.speaker for s in segments):
        return transcription.text
    turns = [
        f"{_turn_prefix(s)} {s.text.strip()}"
        for s in segments
        if s.text and s.text.strip()
    ]
    return "\n".join(turns) or transcription.text


def _consensus_speaker(segments: list[Segment]) -> SpeakerRole | None:
    """Si todos los segmentos seleccionados comparten speaker → lo devuelve.

    SPEAKER_00/SPEAKER_01 son clusters de diarizacion, no roles clinicos
    confirmados; se propagan como unknown.
    Mixto o sin etiqueta → None.
    """
    if not segments:
        return None
    speakers = {s.speaker for s in segments if s.speaker}
    if len(speakers) != 1:
        return None
    raw = next(iter(speakers))
    return _coerce_speaker(raw)


def apply_audio_evidence_alignment(
    suggestions: list[SuggestionV1],
    transcription: TranscriptResult,
) -> list[SuggestionV1]:
    """Agrega timestamps + speaker a sugerencias v1 usando segmentos.

    - Si la evidencia se alinea con uno o varios segmentos: poblar
      `audio_start`/`audio_end` y, si los segmentos comparten speaker,
      poblar `suggestion.speaker`.
    - Si NO se alinea: anadir `no_audio_timestamp` a risk_flags. Nunca inventa
      timestamps ni speakers.
    """
    aligned: list[SuggestionV1] = []
    segments = list(transcription.segments)

    for suggestion in suggestions:
        alignment = align_evidence_to_segments(
            _strip_turn_prefix(suggestion.evidence),
            segments,
        )
        if alignment is None:
            flags = list(suggestion.risk_flags)
            if "no_audio_timestamp" not in flags:
                flags.append("no_audio_timestamp")
            aligned.append(suggestion.model_copy(update={"risk_flags": flags}))
            continue

        updates: dict = {
            "audio_start": alignment.audio_start,
            "audio_end": alignment.audio_end,
        }
        # Propagar speaker si el segmento (o ventana) tiene atribucion consensual.
        # No sobreescribimos un speaker ya determinado por otra fuente.
        if suggestion.speaker is None:
            picked_segments = [segments[i] for i in alignment.segment_indexes if 0 <= i < len(segments)]
            speaker = _consensus_speaker(picked_segments)
            if speaker is not None:
                updates["speaker"] = speaker

        aligned.append(suggestion.model_copy(update=updates))
    return aligned


def transcription_meta_v1(transcription: TranscriptResult) -> TranscriptionMetaV1:
    return TranscriptionMetaV1(
        text=transcription.text,
        duration_s=transcription.duration_s,
        rtf=transcription.rtf,
        provider=transcription.provider,
        model=transcription.model,
        language=transcription.language,
        diarized=any(segment.speaker for segment in transcription.segments),
    )
