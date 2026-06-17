"""Guardia anti-alucinacion para sugerencias de LLM.

Modelos pequenos (o entrevista libre con muchas preguntas a la vez) tienden a
"rellenar" todas las preguntas con respuestas inventadas: misma evidencia
copiada, confidence 1.0, codigos sin sustento. Esta guardia es determinista y
no depende de la calidad del modelo:

1. grounding: la evidencia debe aparecer literalmente en la transcripcion.
   Si el modelo invento la cita, se descarta.
2. relevancia: el tema de la pregunta debe estar en la evidencia. Una pregunta
   de "cuero cabelludo normal?" con evidencia "no fumo" no es valida.
3. duplicado: si la MISMA evidencia se reusa en muchas preguntas, es firma de
   alucinacion en masa -> se descartan.

Solo se aplica a la salida de LLM. El extractor heuristico ya filtra por
relevancia internamente.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from app.core.config import get_settings
from app.models.suggestion import AiSuggestion
from app.services.extraction_service import question_topic_present
from app.services.question_family_builder import expand_with_family_context
from app.services.text_utils import normalize_text


logger = logging.getLogger(__name__)


# Si una misma evidencia normalizada se repite en >= N sugerencias, sospecha de
# alucinacion en masa. 2-3 citas compartidas pueden ser legitimas
# ("no fumo ni bebo" -> fuma=No, alcohol=No), asi que el umbral es alto.
DUPLICATE_EVIDENCE_LIMIT = 4

# Confianza maxima que se acepta de un LLM. Un 1.0 crudo no es fiable.
MAX_LLM_CONFIDENCE = 0.95

# Por encima de N preguntas el prompt module-wide ahoga a los modelos: pierden
# el hilo e inventan ids. Pre-filtramos por relevancia al texto antes de llamar.
MODULE_WIDE_NARROW_THRESHOLD = 20

# Fraccion de tokens de la evidencia que deben aparecer en la transcripcion para
# considerarla anclada cuando NO es substring literal. El LLM suele reescribir
# puntuacion/tildes; exigir substring exacto descarta evidencia valida.
FUZZY_GROUNDING_MIN_RATIO = 0.7

# Sinonimos medicos en espanol para expansion de tokens en grounding fuzzy.
# Evita falsos rechazos cuando el paciente usa una variante terminologica del
# concepto preguntado (p.ej. "cardio" en evidencia vs "cardiovascular" en texto).
_MEDICAL_SYNONYMS_ES: dict[str, frozenset[str]] = {
    "cardio": frozenset({"cardiovascular", "corazon", "cardiaco", "cardiopatia", "cardiac"}),
    "cardiovascular": frozenset({"cardio", "corazon", "cardiaco", "cardiopatia"}),
    "corazon": frozenset({"cardio", "cardiovascular", "cardiaco", "infarto"}),
    "alergia": frozenset({"alergico", "alergica", "intolerancia", "reaccion adversa", "hipersensibilidad"}),
    "alergico": frozenset({"alergia", "intolerancia", "no tolero", "reaccion adversa"}),
    "alergica": frozenset({"alergia", "intolerancia", "no tolero"}),
    "fuma": frozenset({"fumador", "tabaco", "cigarrillo", "cigarro", "nicotina", "fumar"}),
    "fumador": frozenset({"fuma", "tabaco", "cigarrillo", "cigarro", "fumar"}),
    "tabaco": frozenset({"fuma", "fumador", "cigarrillo", "cigarro", "fumar"}),
    "cigarrillo": frozenset({"fuma", "fumador", "tabaco", "cigarro"}),
    "operacion": frozenset({"cirugia", "quirurgica", "intervencion", "operado", "operada", "intervenido"}),
    "cirugia": frozenset({"operacion", "quirurgica", "intervencion", "operado", "operada"}),
    "intervencion": frozenset({"operacion", "cirugia", "quirurgica", "operado", "operada"}),
    "operado": frozenset({"operacion", "cirugia", "intervencion", "quirurgico"}),
    "medicamento": frozenset({"medicacion", "farmaco", "pastilla", "tratamiento", "comprimido", "capsula"}),
    "medicacion": frozenset({"medicamento", "farmaco", "pastilla", "tratamiento", "comprimido"}),
    "farmaco": frozenset({"medicamento", "medicacion", "pastilla", "tratamiento"}),
    "pastilla": frozenset({"medicamento", "medicacion", "farmaco", "comprimido"}),
    "ejercicio": frozenset({"deporte", "actividad", "entrenamiento", "entreno", "gimnasio", "fisico"}),
    "deporte": frozenset({"ejercicio", "actividad", "entrenamiento", "gimnasio", "atletismo"}),
    "entreno": frozenset({"ejercicio", "deporte", "entrenamiento", "gimnasio"}),
    "padre": frozenset({"paterno", "progenitor", "papa", "viejo", "progenitores"}),
    "madre": frozenset({"materno", "progenitora", "mama", "vieja", "progenitores"}),
    "familiar": frozenset({"padre", "madre", "hermano", "abuelo", "familia", "hereditario"}),
    "hipertension": frozenset({"tension alta", "presion alta", "hipertenso", "hipertensa", "hta"}),
    "hipertenso": frozenset({"hipertension", "tension alta", "presion alta", "hta"}),
    "diabetes": frozenset({"diabetico", "diabetica", "glucosa", "azucar", "insulina"}),
    "diabetico": frozenset({"diabetes", "glucosa", "azucar", "insulina"}),
    "alcohol": frozenset({"bebida", "alcoholica", "bebo", "bebedor", "vino", "cerveza", "ron", "bebidas"}),
    "bebida": frozenset({"alcohol", "alcoholica", "bebedor", "vino", "cerveza", "ron"}),
    "asma": frozenset({"asmatico", "asmatica", "bronquios", "inhalador", "bronquial"}),
    "colesterol": frozenset({"lipidos", "trigliceridos", "estatina", "hipercolesterolemia"}),
    "trabajo": frozenset({"laboral", "empleo", "profesion", "oficio", "ocupacion", "empresa"}),
    "laboral": frozenset({"trabajo", "empleo", "profesion", "oficio", "ocupacion"}),
}


def _expand_token(token: str) -> frozenset[str]:
    """Expande un token con sus sinonimos medicos."""
    synonyms = _MEDICAL_SYNONYMS_ES.get(token, frozenset())
    return frozenset({token}) | synonyms


def _evidence_grounded(evidence_norm: str, norm_text: str, *, fuzzy: bool) -> bool:
    """True si la evidencia esta anclada en la transcripcion.

    Substring literal primero. Si `fuzzy`, acepta tambien cobertura de tokens
    >= FUZZY_GROUNDING_MIN_RATIO con expansion de sinonimos medicos (tolera
    reescritura menor del modelo y variantes terminologicas del paciente).
    """
    if not evidence_norm:
        return False
    if evidence_norm in norm_text:
        return True
    if not fuzzy:
        return False
    tokens = [tok for tok in evidence_norm.split() if len(tok) > 2]
    if not tokens:
        return False
    hits = 0
    for tok in tokens:
        expanded = _expand_token(tok)
        if any(syn in norm_text for syn in expanded):
            hits += 1
    return hits / len(tokens) >= FUZZY_GROUNDING_MIN_RATIO


def narrow_questions_by_relevance(
    questions: list[dict[str, Any]],
    transcript: str,
) -> list[dict[str, Any]]:
    """Reduce las preguntas a las cuyo tema aparece en la transcripcion.

    Entrevista libre = modulo completo (100+ preguntas). Mandarlas todas al LLM
    produce alucinacion. Este pre-filtro deja solo candidatas plausibles segun la
    misma heuristica de relevancia que valida la evidencia, recortando el prompt.
    """
    norm_text = normalize_text(transcript or "")
    if not norm_text:
        return list(questions)
    selected = [q for q in questions if question_topic_present(q, norm_text)]
    return expand_with_family_context(questions, selected)


def _rejection_reason(
    s: AiSuggestion,
    question: Any,
    evidence: str,
    norm_text: str,
    ev_counts: Counter,
    *,
    fuzzy_grounding: bool,
    relevance_scope: str,
    lenient: bool,
) -> str | None:
    """Devuelve el motivo de rechazo o None si la sugerencia es valida."""
    if question is None:
        return "unknown_question"
    if not s.selected_codes and not (s.free_text or "").strip():
        # Algunos modelos (ej. scout) emiten entradas con selected_codes vacio.
        return "no_codes"
    if not evidence:
        return "no_evidence"
    if not _evidence_grounded(evidence, norm_text, fuzzy=fuzzy_grounding):
        return "evidence_not_grounded"
    if ev_counts[evidence] >= DUPLICATE_EVIDENCE_LIMIT:
        return "duplicate_evidence"
    relevance_target = norm_text if relevance_scope == "transcript" else evidence
    if not lenient and not question_topic_present(question, relevance_target):
        return "evidence_irrelevant"
    return None


def ground_and_filter_llm(
    suggestions: list[AiSuggestion],
    questions: list[dict[str, Any]],
    transcript: str,
    *,
    fuzzy_grounding: bool | None = None,
    relevance_scope: str | None = None,
    lenient: bool | None = None,
    lenient_question_ids: set[str] | None = None,
) -> list[AiSuggestion]:
    """Filtra sugerencias LLM no ancladas/irrelevantes. Acota confidence.

    Calibracion (defaults desde settings, override por kwargs en tests):
    - fuzzy_grounding: ancla por cobertura de tokens si no hay substring literal.
      Tolera que el LLM reescriba puntuacion/tildes de la cita.
    - relevance_scope: "transcript" valida el tema contra todo el transcript
      (no solo la cita). Audios con preguntas reformuladas producen respuestas
      validas sin la palabra-tema -> exigirla en la cita las descartaba.
    - lenient: omite el check de relevancia (solo exige anclaje al transcript).
    - lenient_question_ids: aplica modo lenient solo para estas preguntas concretas
      (p.ej. preguntas que el medico pregunto explicitamente en el pase de recovery).
    """
    if not suggestions:
        return []

    settings = get_settings()
    if fuzzy_grounding is None:
        fuzzy_grounding = settings.extraction_fuzzy_grounding
    if relevance_scope is None:
        relevance_scope = settings.extraction_relevance_scope
    if lenient is None:
        lenient = settings.extraction_lenient_mode

    by_id = {q.get("id"): q for q in questions}
    norm_text = normalize_text(transcript or "")
    ev_counts = Counter(
        normalize_text(s.evidence or "") for s in suggestions if s.evidence
    )

    kept: list[AiSuggestion] = []
    dropped: list[tuple[str, str]] = []

    for s in suggestions:
        question = by_id.get(s.question_id)
        evidence = normalize_text(s.evidence or "")
        is_lenient = lenient or bool(lenient_question_ids and s.question_id in lenient_question_ids)

        reason = _rejection_reason(
            s, question, evidence, norm_text, ev_counts,
            fuzzy_grounding=fuzzy_grounding,
            relevance_scope=relevance_scope,
            lenient=is_lenient,
        )

        if reason:
            dropped.append((s.question_id, reason))
            continue

        if s.confidence > MAX_LLM_CONFIDENCE:
            s = s.model_copy(update={"confidence": MAX_LLM_CONFIDENCE})
        kept.append(s)

    if dropped:
        logger.info(
            "Guardia LLM descarto %d/%d sugerencias: %s",
            len(dropped),
            len(suggestions),
            dropped[:10],
        )
    return kept


__all__ = [
    "ground_and_filter_llm",
    "narrow_questions_by_relevance",
    "DUPLICATE_EVIDENCE_LIMIT",
    "MAX_LLM_CONFIDENCE",
    "MODULE_WIDE_NARROW_THRESHOLD",
]
