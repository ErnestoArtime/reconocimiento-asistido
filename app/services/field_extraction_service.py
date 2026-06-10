from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.models.suggestion import AiSuggestion
from app.services.extraction_service import extract_from_text, merge_suggestions
from app.services.question_family_builder import chunk_questions_by_family


ExtractorFn = Callable[
    [str, str, str, list[dict[str, Any]]],
    list[AiSuggestion],
]


def extract_field(
    *,
    text: str,
    module: str,
    section: str,
    question: dict[str, Any],
    extractor: ExtractorFn = extract_from_text,
) -> list[AiSuggestion]:
    """Extrae una sola pregunta manteniendo codigos acotados a ese campo."""
    return extractor(text, module, section, [question])


def extract_small_batches(
    *,
    text: str,
    module: str,
    section: str,
    questions: Sequence[dict[str, Any]],
    batch_size: int = 6,
    extractor: ExtractorFn = extract_from_text,
    max_workers: int = 1,
) -> list[AiSuggestion]:
    """Extrae por lotes pequenos y fusiona por `question_id`.

    El primer lote que cubre una pregunta prevalece. Esto mantiene la semantica
    de `merge_suggestions` y evita duplicados si un extractor solapa resultados.

    `max_workers` > 1 lanza los lotes en paralelo (ThreadPoolExecutor). Las
    llamadas a proveedores LLM son I/O-bound (httpx), asi que el wall time pasa
    de la suma de lotes al maximo por oleada. El orden de fusion se preserva (el
    primer lote que cubre una pregunta sigue prevaleciendo) porque `map` mantiene
    el orden de entrada.
    """
    if batch_size < 1:
        raise ValueError("batch_size debe ser >= 1")

    batches = chunk_questions_by_family(questions, batch_size)
    if not batches:
        return []

    if max_workers > 1 and len(batches) > 1:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(batches))) as pool:
            results = list(
                pool.map(
                    lambda batch: extractor(text, module, section, list(batch)),
                    batches,
                )
            )
    else:
        results = [extractor(text, module, section, list(batch)) for batch in batches]

    merged: list[AiSuggestion] = []
    for suggestions in results:
        merged = merge_suggestions(merged, suggestions)
    return merged


def chunk_questions(
    questions: Sequence[dict[str, Any]],
    batch_size: int,
) -> list[list[dict[str, Any]]]:
    if batch_size < 1:
        raise ValueError("batch_size debe ser >= 1")
    return [
        list(questions[index : index + batch_size])
        for index in range(0, len(questions), batch_size)
    ]
