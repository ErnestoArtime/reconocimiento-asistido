"""Recuperacion de pasajes relevantes via BM25 para reducir ruido en la extraccion LLM.

Divide el transcript en oraciones y puntua cada una contra los tokens de las
preguntas de la seccion (texto + etiquetas de codigos). El LLM recibe solo las
top-K oraciones mas relevantes.

La evidence de grounding SIEMPRE se verifica contra el transcript original
completo (sin BM25), por lo que este modulo no afecta a la precision del
anclaje anti-alucinacion.

Dependencia opcional: rank_bm25. Si no esta instalado, devuelve el transcript
intacto (cero degradacion, el modulo es un noop transparente).
"""
from __future__ import annotations

import re

from app.services.text_utils import normalize_text


def retrieve_relevant_passages(
    transcript: str,
    questions: list[dict],
    top_k: int = 15,
) -> str:
    """Devuelve las top_k oraciones del transcript mas relevantes para las preguntas.

    Si rank_bm25 no esta instalado o el transcript tiene <= top_k oraciones,
    devuelve el transcript original intacto.
    """
    try:
        from rank_bm25 import BM25Okapi  # noqa: PLC0415
    except ImportError:
        return transcript

    sentences = _split_sentences(transcript)
    if len(sentences) <= top_k:
        return transcript

    query_tokens = _build_query_tokens(questions)
    if not query_tokens:
        return transcript

    tokenized_corpus = [normalize_text(s).split() for s in sentences]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(query_tokens)

    top_indices = sorted(
        range(len(scores)), key=lambda i: scores[i], reverse=True
    )[:top_k]
    top_indices_ordered = sorted(top_indices)

    return " ".join(sentences[i] for i in top_indices_ordered)


def _split_sentences(text: str) -> list[str]:
    normalized = text.replace(";", ".").replace("\n", " ")
    parts = re.split(r"(?<=[.!?])\s+", normalized)
    return [p.strip() for p in parts if len(p.strip()) > 5]


def _build_query_tokens(questions: list[dict]) -> list[str]:
    tokens: set[str] = set()
    for q in questions:
        for token in normalize_text(q.get("text", "")).split():
            if len(token) > 3:
                tokens.add(token)
        for label in (q.get("codes") or {}).values():
            norm_label = normalize_text(label)
            if "#texto" in norm_label:
                continue
            for token in norm_label.split():
                if len(token) > 3:
                    tokens.add(token)
    return list(tokens)
