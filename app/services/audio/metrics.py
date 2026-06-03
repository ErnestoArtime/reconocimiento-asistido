"""Metricas de calidad para transcripcion.

WER: word error rate (jiwer si esta; fallback Levenshtein simple).
CER: character error rate.
RTF: real time factor = processing_time / audio_duration.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass


logger = logging.getLogger(__name__)


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = _strip_accents(text)
    text = _PUNCT_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _edit_distance(a: list[str] | str, b: list[str] | str) -> int:
    # Levenshtein clasico O(len(a)*len(b))
    if isinstance(a, str):
        a = list(a)
    if isinstance(b, str):
        b = list(b)
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


@dataclass
class QualityScore:
    wer: float
    cer: float
    ref_words: int
    hyp_words: int


def score(reference: str, hypothesis: str) -> QualityScore:
    ref_norm = normalize(reference)
    hyp_norm = normalize(hypothesis)

    try:
        import jiwer  # type: ignore

        wer = float(jiwer.wer(ref_norm, hyp_norm))
        cer = float(jiwer.cer(ref_norm, hyp_norm))
    except Exception as exc:  # noqa: BLE001
        logger.debug("jiwer no disponible (%s), fallback Levenshtein", exc)
        ref_words = ref_norm.split()
        hyp_words = hyp_norm.split()
        wer = _edit_distance(ref_words, hyp_words) / max(len(ref_words), 1)
        cer = _edit_distance(ref_norm, hyp_norm) / max(len(ref_norm), 1)

    return QualityScore(
        wer=wer,
        cer=cer,
        ref_words=len(ref_norm.split()),
        hyp_words=len(hyp_norm.split()),
    )
