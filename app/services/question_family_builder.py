from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from app.services.text_utils import normalize_text


def _transition_parents(questions: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id = {q.get("id"): q for q in questions if q.get("id")}
    incoming: dict[str, list[tuple[dict[str, Any], str]]] = defaultdict(list)
    for question in questions:
        targets = set((question.get("transitions") or {}).values())
        if len(targets) < 2:
            continue
        for code, target_id in (question.get("transitions") or {}).items():
            if target_id in by_id and _looks_like_detail_question(by_id[target_id]):
                incoming[target_id].append((question, code))

    parents: dict[str, dict[str, Any]] = {}
    for child_id, links in incoming.items():
        parent = links[0][0]
        parent_id = parent.get("id")
        if not parent_id:
            continue
        codes = [code for linked_parent, code in links if linked_parent.get("id") == parent_id]
        parents[child_id] = {
            "parent_question_id": parent_id,
            "parent_question": parent.get("text", ""),
            "required_parent_codes": codes,
        }
    return parents


def _looks_like_detail_question(question: dict[str, Any]) -> bool:
    text = normalize_text(question.get("text", ""))
    detail_prefixes = (
        "que ",
        "en que ",
        "a que ",
        "recuerda cuando",
        "cuando ",
        "cuantos ",
    )
    return text.startswith(detail_prefixes)


def _infer_subject(question: dict[str, Any], parent_text: str = "") -> str:
    text = normalize_text(" ".join([question.get("text", ""), parent_text]))
    if "padre" in text:
        return "father"
    if "madre" in text:
        return "mother"
    if "herman" in text:
        return "sibling"
    return "patient"


def _infer_temporal_scope(question: dict[str, Any]) -> str | None:
    text = normalize_text(question.get("text", ""))
    if any(token in text for token in ["actual", "actualmente", "fuma", "toma alguna medicacion"]):
        return "current"
    if any(token in text for token in ["anterior", "anteriormente", "ha trabajado", "ha fumado", "ha consumido"]):
        return "past"
    if any(token in text for token in ["ha padecido", "ha tenido", "hasta la fecha"]):
        return "ever"
    return None


def _context_for(question: dict[str, Any], parent_text: str = "") -> str:
    section = question.get("section") or ""
    text = question.get("text") or ""
    if parent_text:
        return f"{section}: detalle dependiente de '{parent_text}' para '{text}'"
    return f"{section}: {text}" if section else text


def enrich_questions_with_ai_context(
    questions: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Devuelve copias con metadatos derivados para el prompt IA.

    No modifica el cuestionario fuente. Las dependencias se infieren de
    transiciones ramificadas: si una respuesta de un padre lleva a una pregunta
    hija y otra respuesta lleva a otra ruta, la hija conserva ese padre y los
    codigos que la activan.
    """
    parents = _transition_parents(questions)
    enriched: list[dict[str, Any]] = []
    for question in questions:
        item = dict(question)
        parent = parents.get(question.get("id"), {})
        if parent:
            item.update(parent)
        parent_text = item.get("parent_question") or ""
        item.setdefault("ai_context", _context_for(item, parent_text))
        item.setdefault("subject", _infer_subject(item, parent_text))
        temporal_scope = _infer_temporal_scope(item)
        if temporal_scope:
            item.setdefault("temporal_scope", temporal_scope)
        enriched.append(item)
    return enriched


def expand_with_family_context(
    questions: Sequence[dict[str, Any]],
    selected: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Preserva padres e hijas inmediatas de las preguntas seleccionadas."""
    enriched = enrich_questions_with_ai_context(questions)
    by_id = {q.get("id"): q for q in enriched if q.get("id")}
    children: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for question in enriched:
        parent_id = question.get("parent_question_id")
        if parent_id:
            children[parent_id].append(question)

    keep: set[str] = set()
    for question in selected:
        question_id = question.get("id")
        if not question_id:
            continue
        keep.add(question_id)
        parent_id = by_id.get(question_id, {}).get("parent_question_id")
        if parent_id:
            keep.add(parent_id)
        for child in children.get(question_id, []):
            if child.get("id"):
                keep.add(child["id"])

    return [question for question in enriched if question.get("id") in keep]


def chunk_questions_by_family(
    questions: Sequence[dict[str, Any]],
    batch_size: int,
) -> list[list[dict[str, Any]]]:
    """Agrupa preguntas sin separar padres de hijas inmediatas."""
    if batch_size < 1:
        raise ValueError("batch_size debe ser >= 1")

    enriched = enrich_questions_with_ai_context(questions)
    by_id = {q.get("id"): q for q in enriched if q.get("id")}
    children: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for question in enriched:
        parent_id = question.get("parent_question_id")
        if parent_id in by_id:
            children[parent_id].append(question)

    families: list[list[dict[str, Any]]] = []
    seen: set[str] = set()
    for question in enriched:
        question_id = question.get("id")
        if not question_id or question_id in seen:
            continue
        parent_id = question.get("parent_question_id")
        if parent_id in by_id and parent_id not in seen:
            continue
        family = [question]
        seen.add(question_id)
        for child in children.get(question_id, []):
            child_id = child.get("id")
            if child_id and child_id not in seen:
                family.append(child)
                seen.add(child_id)
        families.append(family)

    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for family in families:
        if current and len(current) + len(family) > batch_size:
            batches.append(current)
            current = []
        current.extend(family)
        if len(current) >= batch_size:
            batches.append(current)
            current = []
    if current:
        batches.append(current)
    return batches


__all__ = [
    "chunk_questions_by_family",
    "enrich_questions_with_ai_context",
    "expand_with_family_context",
]
