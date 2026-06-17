"""Detecta qué preguntas del formulario el médico cubrió explícitamente.

El resultado alimenta el pase de recuperación en routes_ia.py: preguntas que el
médico hizo pero el extractor principal no capturó se re-extraen con guardrails
más permisivos (lenient_question_ids), garantizando cobertura de lo preguntado.

Flujo:
  1. Llamada LLM liviana -> lista de temas preguntados por el médico (palabras clave).
  2. Fuzzy-matching de cada tema contra las preguntas del formulario.
  3. Devuelve set[question_id] de las preguntas cubiertas.

Falla en silencio (devuelve set vacío) para no bloquear el flujo principal.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.extraction_service import _topic_tokens
from app.services.text_utils import normalize_text


logger = logging.getLogger(__name__)


def _parse_topics(raw: str) -> list[str]:
    if not raw:
        return []
    try:
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*", "", cleaned).strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        data = json.loads(cleaned)
        temas = data.get("temas", [])
        if isinstance(temas, list):
            return [str(t).strip() for t in temas if t and isinstance(t, str)]
    except Exception:  # noqa: BLE001
        pass
    return []


def _topic_overlaps_question(doctor_topic_norm: str, question: dict[str, Any]) -> bool:
    """True si el tema del médico se solapa con el tema de la pregunta del formulario."""
    question_text_norm = normalize_text(question.get("text", ""))

    # Reutiliza la heurística de topic tokens del extractor
    topic_tokens = _topic_tokens(question_text_norm)
    if topic_tokens and any(tok in doctor_topic_norm for tok in topic_tokens):
        return True

    # Solapamiento directo de palabras sustantivas (len > 3)
    topic_words = {w for w in doctor_topic_norm.split() if len(w) > 3}
    question_words = {w for w in question_text_norm.split() if len(w) > 3}
    return bool(topic_words & question_words)


def detect_covered_question_ids(
    transcript: str,
    questions: list[dict[str, Any]],
    provider: Any,
) -> set[str]:
    """Devuelve los IDs de preguntas que el médico cubrió explícitamente.

    Usa LLM para extraer temas preguntados, luego fuzzy-match contra el formulario.
    Devuelve set vacío si el provider no soporta detección o si falla la llamada.
    """
    if not hasattr(provider, "detect_doctor_topics"):
        return set()

    try:
        raw = provider.detect_doctor_topics(transcript)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Doctor question detector: llamada LLM fallida: %s", exc)
        return set()

    doctor_topics = _parse_topics(raw)
    if not doctor_topics:
        logger.debug("Doctor question detector: sin temas detectados en la transcripcion")
        return set()

    doctor_topics_norm = [normalize_text(t) for t in doctor_topics]

    covered: set[str] = set()
    for question in questions:
        q_id = question.get("id")
        if not q_id:
            continue
        if any(_topic_overlaps_question(t, question) for t in doctor_topics_norm):
            covered.add(q_id)

    logger.info(
        "Doctor question detector: %d temas -> %d/%d preguntas cubiertas",
        len(doctor_topics),
        len(covered),
        len(questions),
    )
    return covered


__all__ = ["detect_covered_question_ids"]
