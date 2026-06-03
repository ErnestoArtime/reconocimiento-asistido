from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from app.models.extraction_contract import GraphReportV1


class GraphSuggestion(Protocol):
    question_id: str
    selected_codes: list[str]


def build_graph_report(
    *,
    module_entry_question_id: str | None,
    questions: Sequence[dict[str, Any]],
    suggestions: Sequence[GraphSuggestion],
) -> GraphReportV1:
    """Recorre una seccion del cuestionario segun las respuestas sugeridas.

    El JSON global puede tener un `entry_question_id` fuera de la seccion que se
    esta procesando. En ese caso se usa la primera pregunta de la seccion como
    entrada local, que es lo que espera el flujo MVP por seccion.
    """
    if not questions:
        return GraphReportV1()

    questions_by_id = {question["id"]: question for question in questions}
    question_order = [question["id"] for question in questions]
    entry_question_id = (
        module_entry_question_id
        if module_entry_question_id in questions_by_id
        else question_order[0]
    )
    suggestion_by_id = {suggestion.question_id: suggestion for suggestion in suggestions}

    path: list[str] = []
    accepted_question_ids: list[str] = []
    missing_required: list[str] = []
    visited: set[str] = set()

    current_id: str | None = entry_question_id
    while current_id and current_id in questions_by_id and current_id not in visited:
        visited.add(current_id)
        path.append(current_id)

        suggestion = suggestion_by_id.get(current_id)
        if suggestion:
            accepted_question_ids.append(current_id)
            current_id = _next_from_answer(questions_by_id[current_id], suggestion)
            continue

        missing_required.append(current_id)
        current_id = _next_if_unambiguous(questions_by_id[current_id])

    path_set = set(path)
    discarded = [
        {
            "question_id": suggestion.question_id,
            "reason": "not_reachable_from_selected_path",
        }
        for suggestion in suggestions
        if suggestion.question_id not in path_set
    ]

    return GraphReportV1(
        entry_question_id=entry_question_id,
        path=path,
        accepted_question_ids=accepted_question_ids,
        discarded=discarded,
        missing_required=missing_required,
        conflicts=[],
    )


def _next_from_answer(question: dict[str, Any], suggestion: GraphSuggestion) -> str | None:
    transitions = question.get("transitions", {})
    for code in suggestion.selected_codes:
        target = transitions.get(code)
        if target:
            return target
    return None


def _next_if_unambiguous(question: dict[str, Any]) -> str | None:
    transitions = question.get("transitions", {})
    targets = {target for target in transitions.values() if target}
    if len(targets) == 1:
        return next(iter(targets))
    return None
