"""Contrato API versionado para extraccion clinica desde voz/texto.

`schema_version` sigue el formato YYYY-MM-feature-vN.
- Cambios incompatibles -> bump de version.
- Cambios aditivos (campos opcionales nuevos) -> misma version.

Este modulo NO depende de Pydantic v1 ni de codigo legacy. El adaptador
hacia `app.models.suggestion.AiSuggestion` esta en `app.models.legacy_adapter`.

Referencias:
- docs/API_CONTRACT_V1.md
- docs/API_CONTRACT_V1_REFERENCE.md
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "2026-05-voice-form-v1"


# --- Vocabularios cerrados -----------------------------------------------------

TechnicalStatus = Literal[
    "valid",                 # sugerencia bien formada, codigo valido, evidencia presente
    "invalid_code",          # el modelo intento un codigo que no existe en la pregunta
    "discarded_by_graph",    # la pregunta no es alcanzable segun el recorrido
    "missing_evidence",      # no hay evidencia textual suficiente
    "parse_error",           # respuesta del LLM no parseable (JSON malformado, etc.)
]

ReviewStatus = Literal[
    "pending",      # esperando revision humana
    "accepted",     # aceptada tal cual
    "edited",       # aceptada con modificaciones del revisor
    "rejected",     # descartada por el revisor
]

RiskFlag = Literal[
    "low_confidence",            # confidence < umbral
    "free_text",                 # respuesta libre, requiere revision manual
    "conflict",                  # contradice una respuesta ya aceptada
    "uncertain_negation",        # negacion ambigua o uncertain temporality
    "no_audio_timestamp",        # evidencia textual sin localizacion en audio
    "speaker_not_expected",      # speaker incoherente con modulo (medico en history, etc.)
    "online_provider_used",      # extraccion con proveedor externo (no LOCAL_ONLY)
    "historical_temporality",    # respuesta refleja pasado, no presente
]

SpeakerRole = Literal["medico", "paciente", "acompanante", "unknown"]

ModuleName = Literal["history", "exam"]


# --- Modelos base -------------------------------------------------------------


class SuggestionV1(BaseModel):
    """Sugerencia de IA validada contra una pregunta concreta del cuestionario."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    module: ModuleName | None = None
    section: str | None = None
    question_text: str | None = None
    question_type: str | None = None
    selected_codes: list[str] = Field(default_factory=list)
    selected_labels: list[str] = Field(default_factory=list)
    free_text: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = ""

    # Localizacion temporal en el audio fuente (None si no se pudo alinear)
    audio_start: float | None = Field(default=None, ge=0.0)
    audio_end: float | None = Field(default=None, ge=0.0)

    # Atribucion del hablante segun diarizacion. None cuando no se diariza.
    speaker: SpeakerRole | None = None

    # Estados ortogonales: tecnico (de la IA) y humano (del revisor).
    technical_status: TechnicalStatus = "valid"
    review_status: ReviewStatus = "pending"

    # Banderas no excluyentes que disparan revision o degradan confianza.
    risk_flags: list[RiskFlag] = Field(default_factory=list)

    # Texto opcional con la razon de un descarte / faltante / parse error.
    reason: str | None = None


class GraphReportV1(BaseModel):
    """Resultado del recorrido determinista del grafo del cuestionario."""

    model_config = ConfigDict(extra="forbid")

    entry_question_id: str | None = None
    path: list[str] = Field(default_factory=list)
    accepted_question_ids: list[str] = Field(default_factory=list)
    discarded: list[dict] = Field(default_factory=list)        # {question_id, reason}
    missing_required: list[str] = Field(default_factory=list)
    conflicts: list[dict] = Field(default_factory=list)        # {question_id, current, new}


class QualityReportV1(BaseModel):
    """Resumen operativo por ejecucion. Util para UI, logs y golden bench."""

    model_config = ConfigDict(extra="forbid")

    total_questions_considered: int = 0
    suggestions_valid: int = 0
    suggestions_needing_review: int = 0

    # Conteos de descartes
    discarded_invalid_code: int = 0
    discarded_by_graph: int = 0
    discarded_by_validator_count: int = 0

    # Estado de la pregunta
    missing_required: int = 0
    evidence_without_timestamp: int = 0

    # Salud del extractor (introspeccion del LLM)
    schema_parse_fail_count: int = 0
    empty_generation_count: int = 0

    # Origen
    provider: str = ""
    model: str = ""
    profile: str = "demo"  # demo | prototype_local | production


class TranscriptionMetaV1(BaseModel):
    """Metadatos de la transcripcion cuando la entrada fue audio."""

    model_config = ConfigDict(extra="forbid")

    text: str = ""
    duration_s: float = 0.0
    rtf: float = 0.0
    provider: str = ""
    model: str = ""
    language: str = "es"
    diarized: bool = False


class ExtractionResponseV1(BaseModel):
    """Respuesta unificada de los endpoints `/api/v1/...` de extraccion."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    module: ModuleName
    section: str
    suggestions: list[SuggestionV1] = Field(default_factory=list)
    graph_report: GraphReportV1 = Field(default_factory=GraphReportV1)
    quality_report: QualityReportV1 = Field(default_factory=QualityReportV1)
    transcription: TranscriptionMetaV1 | None = None

    # Resumen clinico estructurado (solo si IA_CLINICAL_SUMMARY_ENABLED). No es
    # fuente de evidencia: las citas siguen ancladas al transcript original.
    clinical_summary: str | None = None


__all__ = [
    "SCHEMA_VERSION",
    "TechnicalStatus",
    "ReviewStatus",
    "RiskFlag",
    "SpeakerRole",
    "ModuleName",
    "SuggestionV1",
    "GraphReportV1",
    "QualityReportV1",
    "TranscriptionMetaV1",
    "ExtractionResponseV1",
]
