"""Adaptador entre el contrato legacy (`AiSuggestion`/`ValidatedSuggestion`) y v1.

Permite que endpoints existentes sigan emitiendo el formato antiguo mientras
los nuevos endpoints `/api/v1/...` emiten `ExtractionResponseV1`. La conversion
es bidireccional pero NO simetrica:

- `legacy_to_v1()` enriquece con defaults seguros (`technical_status=valid`,
  `review_status=pending`, sin timestamps).
- `v1_to_legacy()` aplasta info que el contrato viejo no representa
  (risk_flags, audio timestamps, quality_report).

Uso esperado durante migracion:

    legacy = ollama.extract(...)            # devuelve list[AiSuggestion]
    v1_suggestions = [legacy_to_v1(s) for s in legacy]
    response = ExtractionResponseV1(
        module=...,
        section=...,
        suggestions=v1_suggestions,
        quality_report=build_quality_report(...),
    )
"""
from __future__ import annotations

from app.models.extraction_contract import (
    QualityReportV1,
    ReviewStatus,
    RiskFlag,
    SpeakerRole,
    SuggestionV1,
    TechnicalStatus,
)
from app.models.suggestion import AiSuggestion, ValidatedSuggestion


_LEGACY_STATUS_TO_RISK: dict[str, list[RiskFlag]] = {
    "suggested": [],
    "low_confidence": ["low_confidence"],
    "conflict": ["conflict"],
}


def _coerce_speaker(value: str | None) -> SpeakerRole | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"medico", "médico", "doctor"}:
        return "medico"
    if normalized in {"paciente", "patient"}:
        return "paciente"
    if normalized in {"acompanante", "acompañante", "companion"}:
        return "acompanante"
    if normalized in {"unknown", "?", ""}:
        return "unknown"
    if normalized.startswith("speaker_"):
        return "unknown"
    return "unknown"


def legacy_to_v1(
    legacy: AiSuggestion | ValidatedSuggestion,
    *,
    audio_start: float | None = None,
    audio_end: float | None = None,
    extra_flags: list[RiskFlag] | None = None,
    technical_status: TechnicalStatus = "valid",
    review_status: ReviewStatus = "pending",
) -> SuggestionV1:
    """Convierte una sugerencia legacy a v1.

    Si `legacy` es `ValidatedSuggestion`, hereda `selected_labels`.
    Los timestamps de audio se pasan por kwargs (el legacy no los tenia).
    """
    selected_labels: list[str] = []
    module: str | None = None
    section: str | None = None
    question_text: str | None = None
    question_type: str | None = None
    if isinstance(legacy, ValidatedSuggestion):
        selected_labels = list(legacy.selected_labels)
        module = legacy.module or None
        section = legacy.section or None
        question_text = legacy.question_text or None
        question_type = legacy.question_type or None

    risk_flags: list[RiskFlag] = list(_LEGACY_STATUS_TO_RISK.get(legacy.status, []))
    if extra_flags:
        for flag in extra_flags:
            if flag not in risk_flags:
                risk_flags.append(flag)

    # Sin timestamp y la fuente fue audio -> bandera.
    if (audio_start is None or audio_end is None) and "no_audio_timestamp" not in risk_flags:
        # NO la agregamos aqui automaticamente: el caller decide si la fuente
        # fue audio. Si todo viene de texto, no aplica esta bandera.
        pass

    if legacy.free_text and "free_text" not in risk_flags:
        risk_flags.append("free_text")

    return SuggestionV1(
        question_id=legacy.question_id,
        module=module,  # type: ignore[arg-type]
        section=section,
        question_text=question_text,
        question_type=question_type,
        selected_codes=list(legacy.selected_codes),
        selected_labels=selected_labels,
        free_text=legacy.free_text,
        confidence=legacy.confidence,
        evidence=legacy.evidence,
        evidence_turn_ids=list(legacy.evidence_turn_ids),
        audio_start=audio_start,
        audio_end=audio_end,
        speaker=_coerce_speaker(legacy.speaker),
        speaker_cluster=legacy.speaker_cluster,
        technical_status=technical_status,
        review_status=review_status,
        risk_flags=risk_flags,
        reason=None,
    )


def v1_to_legacy(suggestion: SuggestionV1) -> AiSuggestion:
    """Conversion inversa minima. Util para tests roundtrip y compatibilidad.

    Aplana: descarta `audio_start/end`, `risk_flags` (excepto conflict/low_conf
    que se mapean a `status`), `technical_status`, `review_status`, `reason`.
    """
    status = "suggested"
    if "conflict" in suggestion.risk_flags:
        status = "conflict"
    elif "low_confidence" in suggestion.risk_flags:
        status = "low_confidence"

    return AiSuggestion(
        question_id=suggestion.question_id,
        selected_codes=list(suggestion.selected_codes),
        free_text=suggestion.free_text,
        confidence=suggestion.confidence,
        evidence=suggestion.evidence,
        evidence_turn_ids=list(suggestion.evidence_turn_ids),
        speaker=suggestion.speaker,
        speaker_cluster=suggestion.speaker_cluster,
        status=status,  # type: ignore[arg-type]
    )


def build_quality_report(
    *,
    questions_considered: int,
    suggestions: list[SuggestionV1],
    provider: str,
    model: str,
    profile: str = "demo",
    extra: dict | None = None,
) -> QualityReportV1:
    """Genera `QualityReportV1` a partir de la lista de sugerencias v1.

    `extra` permite inyectar contadores observados por el provider, ej:
    `{"schema_parse_fail_count": 2, "discarded_by_validator_count": 1}`.
    """
    extra = extra or {}

    valid = sum(1 for s in suggestions if s.technical_status == "valid")
    needing_review = sum(
        1
        for s in suggestions
        if s.review_status == "pending" and s.risk_flags
    )
    discarded_invalid_code = sum(
        1 for s in suggestions if s.technical_status == "invalid_code"
    )
    discarded_by_graph = sum(
        1 for s in suggestions if s.technical_status == "discarded_by_graph"
    )
    missing_evidence = sum(
        1 for s in suggestions if s.technical_status == "missing_evidence"
    )
    evidence_no_ts = sum(
        1
        for s in suggestions
        if s.audio_start is None and "no_audio_timestamp" in s.risk_flags
    )

    return QualityReportV1(
        total_questions_considered=questions_considered,
        suggestions_valid=valid,
        suggestions_needing_review=needing_review,
        discarded_invalid_code=discarded_invalid_code,
        discarded_by_graph=discarded_by_graph,
        discarded_by_validator_count=int(extra.get("discarded_by_validator_count", 0)),
        missing_required=int(extra.get("missing_required", missing_evidence)),
        evidence_without_timestamp=evidence_no_ts,
        schema_parse_fail_count=int(extra.get("schema_parse_fail_count", 0)),
        empty_generation_count=int(extra.get("empty_generation_count", 0)),
        provider=provider,
        model=model,
        profile=profile,
    )


__all__ = [
    "legacy_to_v1",
    "v1_to_legacy",
    "build_quality_report",
]
