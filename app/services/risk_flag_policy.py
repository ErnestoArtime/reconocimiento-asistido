from __future__ import annotations

from collections.abc import Iterable

from app.models.extraction_contract import RiskFlag, SuggestionV1
from app.services.clinical_negation import detect_clinical_negation, has_category


ONLINE_PROVIDERS = {"cloudflare", "both_cloudflare"}
EXPECTED_SPEAKER_BY_MODULE = {
    "history": "paciente",
    "exam": "medico",
}


def apply_risk_flags(
    suggestions: Iterable[SuggestionV1],
    *,
    module: str,
    provider: str,
    low_confidence_threshold: float = 0.6,
    require_audio_timestamps: bool = False,
) -> list[SuggestionV1]:
    """Aplica banderas de riesgo deterministas sin cambiar el estado tecnico."""
    return [
        suggestion.model_copy(
            update={
                "risk_flags": _flags_for_suggestion(
                    suggestion,
                    module=module,
                    provider=provider,
                    low_confidence_threshold=low_confidence_threshold,
                    require_audio_timestamps=require_audio_timestamps,
                )
            }
        )
        for suggestion in suggestions
    ]


def _flags_for_suggestion(
    suggestion: SuggestionV1,
    *,
    module: str,
    provider: str,
    low_confidence_threshold: float,
    require_audio_timestamps: bool,
) -> list[RiskFlag]:
    flags: list[RiskFlag] = list(suggestion.risk_flags)

    if suggestion.confidence < low_confidence_threshold:
        _append_once(flags, "low_confidence")
    if suggestion.free_text:
        _append_once(flags, "free_text")
    negation_findings = detect_clinical_negation(suggestion.evidence or "")
    if has_category(negation_findings, "uncertainty"):
        _append_once(flags, "uncertain_negation")
    if has_category(negation_findings, "historical"):
        _append_once(flags, "historical_temporality")
    if provider in ONLINE_PROVIDERS:
        _append_once(flags, "online_provider_used")
    if require_audio_timestamps and (
        suggestion.audio_start is None or suggestion.audio_end is None
    ):
        _append_once(flags, "no_audio_timestamp")

    expected_speaker = EXPECTED_SPEAKER_BY_MODULE.get(module)
    if (
        expected_speaker
        and suggestion.speaker
        and suggestion.speaker != "unknown"
        and suggestion.speaker != expected_speaker
    ):
        _append_once(flags, "speaker_not_expected")

    return flags


def _append_once(flags: list[RiskFlag], flag: RiskFlag) -> None:
    if flag not in flags:
        flags.append(flag)
