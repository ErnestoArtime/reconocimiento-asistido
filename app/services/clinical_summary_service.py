"""Resumen clinico estructurado a partir del transcript.

Doble uso:
- artefacto para revision medica (pestana "Resumen" en la UI);
- contexto de apoyo para la extraccion LLM.

NO sustituye al transcript como fuente de evidencia. El grounding sigue anclando
cada cita al texto original (ver `extraction_guard`), de modo que el resumen no
puede falsear evidencia verbatim ni timestamps de audio.
"""
from __future__ import annotations

import logging
from typing import Protocol


logger = logging.getLogger(__name__)


class Summarizer(Protocol):
    def summarize(self, text: str) -> str: ...


def generate_clinical_summary(text: str, summarizer: Summarizer) -> str:
    """Devuelve un resumen clinico o cadena vacia si no se pudo generar.

    Nunca lanza: ante texto vacio o fallo del proveedor devuelve "" para que el
    flujo de extraccion continue sin resumen.
    """
    clean = (text or "").strip()
    if not clean:
        return ""
    try:
        return (summarizer.summarize(clean) or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Resumen clinico fallo, se omite: %s", exc)
        return ""


__all__ = ["Summarizer", "generate_clinical_summary"]
