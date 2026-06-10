from typing import Literal

from pydantic import BaseModel, Field


SuggestionStatus = Literal["suggested", "low_confidence", "conflict"]


class AiSuggestion(BaseModel):
    question_id: str
    selected_codes: list[str] = Field(default_factory=list)
    free_text: str | None = None
    confidence: float = Field(ge=0, le=1)
    evidence: str
    evidence_turn_ids: list[str] = Field(default_factory=list)
    speaker: str | None = None
    speaker_cluster: str | None = None
    status: SuggestionStatus = "suggested"


class ValidatedSuggestion(AiSuggestion):
    question_text: str
    question_type: str
    module: str
    section: str
    selected_labels: list[str] = Field(default_factory=list)


class ExtractFromTextRequest(BaseModel):
    module: Literal["history", "exam"]
    # section opcional: None / "" / "*" => extraccion sobre el modulo completo
    # (entrevista libre). Un valor concreto restringe a esa seccion.
    section: str | None = None
    text: str = Field(min_length=1)
    ia_provider: str | None = None  # override puntual del IA_PROVIDER del .env
    ia_model: str | None = None  # override puntual de OLLAMA_MODEL para providers locales
    session_id: str | None = None  # si se pasa y la persistencia esta activa, guarda sugerencias
    transcript_turns: list[dict] | None = None  # uso interno/audio: turnos estructurados para el LLM


class ExtractFromTextResponse(BaseModel):
    module: str
    section: str
    suggestions: list[ValidatedSuggestion]
    extract_ms: float | None = None
    ia_provider_used: str | None = None
    ia_model_used: str | None = None
