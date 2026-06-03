"""Construye un initial_prompt clinico a partir del cuestionario.

Whisper acepta un texto de contexto que mejora la transcripcion de terminos
poco frecuentes. Le pasamos vocabulario extraido del json_IA: enfermedades,
medicaciones, anatomia, hallazgos. Resultado limitado a ~200 tokens.
"""
from __future__ import annotations

from typing import Any


_STOPWORDS = {
    "si", "no", "que", "los", "las", "del", "para", "otros", "otro", "alguna",
    "cual", "presenta", "tiene", "consume", "detecta", "normal", "anormal",
    "derecho", "izquierdo", "ambos", "todos", "ninguno", "texto", "libre",
}


def _is_useful_token(token: str) -> bool:
    if len(token) < 4:
        return False
    if token.lower() in _STOPWORDS:
        return False
    if token.startswith("#"):
        return False
    return True


def build_clinical_prompt(
    questionnaire: dict[str, Any],
    max_terms: int = 80,
    extra: str = "",
) -> str:
    """Devuelve cadena tipo: 'Terminologia: HTA, diabetes, ...'."""
    terms: dict[str, int] = {}

    for _module, mdata in questionnaire.items():
        for question in mdata.get("questions", []):
            for label in question.get("codes", {}).values():
                if not isinstance(label, str):
                    continue
                if "#" in label:
                    continue
                for raw in label.replace(",", " ").replace("/", " ").split():
                    token = raw.strip(".,;:()[]").strip()
                    if _is_useful_token(token):
                        terms[token] = terms.get(token, 0) + 1

    top = sorted(terms.items(), key=lambda item: (-item[1], item[0]))[:max_terms]
    vocab = ", ".join(term for term, _ in top)
    prompt = (
        "Entrevista medica en espanol entre profesional sanitario y paciente. "
        f"Terminologia probable: {vocab}."
    )
    if extra:
        prompt = f"{prompt} {extra.strip()}"
    return prompt
