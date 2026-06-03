from __future__ import annotations

from app.models.extraction_contract import SpeakerRole, SuggestionV1, TranscriptionMetaV1
from app.models.legacy_adapter import _coerce_speaker
from app.services.audio.base import Segment, TranscriptResult
from app.services.audio.evidence_alignment import align_evidence_to_segments


# Hablante cuyo discurso es la fuente clinica por modulo. En history responde el
# paciente; en exam el medico describe los hallazgos.
EXPECTED_SPEAKER_BY_MODULE = {"history": "paciente", "exam": "medico"}


def extraction_text_for_module(transcription: TranscriptResult, module: str) -> str:
    """Texto a extraer. Si hay diarizacion, devuelve solo los turnos del hablante
    esperado del modulo (paciente en history, medico en exam). Sin diarizacion o
    si el filtro queda vacio, devuelve el transcript completo (fallback seguro).
    """
    segments = list(transcription.segments)
    if not any(s.speaker for s in segments):
        return transcription.text
    expected = EXPECTED_SPEAKER_BY_MODULE.get(module)
    if not expected:
        return transcription.text
    picked = [
        s.text.strip()
        for s in segments
        if s.text and s.text.strip() and _coerce_speaker(s.speaker) == expected
    ]
    filtered = " ".join(picked)
    return filtered or transcription.text


def _consensus_speaker(segments: list[Segment]) -> SpeakerRole | None:
    """Si todos los segmentos seleccionados comparten speaker → lo devuelve.

    Mapea SPEAKER_00 → medico, SPEAKER_01 → paciente (convencion proyecto).
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
        alignment = align_evidence_to_segments(suggestion.evidence, segments)
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
