from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import re

from app.services.audio.base import Segment
from app.services.text_utils import normalize_text


@dataclass(frozen=True)
class EvidenceAlignment:
    audio_start: float
    audio_end: float
    segment_indexes: list[int]
    score: float


def align_evidence_to_segments(
    evidence: str,
    segments: Sequence[Segment],
    *,
    window_size: int = 3,
    min_score: float = 0.62,
) -> EvidenceAlignment | None:
    """Localiza una evidencia textual dentro de segmentos transcritos.

    Devuelve None si no hay soporte suficiente. La funcion no inventa tiempos:
    solo usa `start/end` de segmentos que contienen o se parecen a la evidencia.
    """
    normalized_evidence = normalize_text(evidence)
    if not normalized_evidence or not segments:
        return None

    normalized_segments = [normalize_text(segment.text) for segment in segments]

    exact = _match_exact(normalized_evidence, normalized_segments)
    if exact is not None:
        return _alignment_from_indexes(exact, segments, score=1.0)

    fuzzy = _match_fuzzy(
        normalized_evidence,
        normalized_segments,
        window_size=window_size,
        min_score=min_score,
    )
    if fuzzy is None:
        return None
    indexes, score = fuzzy
    return _alignment_from_indexes(indexes, segments, score=score)


def _match_exact(evidence: str, segments: Sequence[str]) -> list[int] | None:
    for index, segment in enumerate(segments):
        if evidence in segment:
            return [index]

    for start in range(len(segments)):
        combined = ""
        indexes: list[int] = []
        for index in range(start, len(segments)):
            combined = f"{combined} {segments[index]}".strip()
            indexes.append(index)
            if evidence in combined:
                return indexes
            if len(combined) > len(evidence) * 2 and len(indexes) > 1:
                break
    return None


def _match_fuzzy(
    evidence: str,
    segments: Sequence[str],
    *,
    window_size: int,
    min_score: float,
) -> tuple[list[int], float] | None:
    evidence_tokens = _meaningful_tokens(evidence)
    if not evidence_tokens:
        return None

    best_indexes: list[int] = []
    best_score = 0.0
    for start in range(len(segments)):
        for end in range(start, min(len(segments), start + window_size)):
            indexes = list(range(start, end + 1))
            window_tokens = _meaningful_tokens(" ".join(segments[start : end + 1]))
            score = len(evidence_tokens & window_tokens) / len(evidence_tokens)
            if score > best_score or (
                score == best_score and best_indexes and len(indexes) < len(best_indexes)
            ):
                best_score = score
                best_indexes = indexes

    if best_score < min_score:
        return None
    return best_indexes, best_score


def _meaningful_tokens(text: str) -> set[str]:
    stopwords = {
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "de",
        "del",
        "por",
        "con",
        "y",
        "o",
        "es",
        "esta",
        "este",
        "actualmente",
    }
    return {
        cleaned
        for token in normalize_text(text).split()
        for cleaned in [re.sub(r"[^a-z0-9]", "", token)]
        if len(token) > 2 and token not in stopwords
        if cleaned
    }


def _alignment_from_indexes(
    indexes: list[int],
    segments: Sequence[Segment],
    *,
    score: float,
) -> EvidenceAlignment:
    selected = [segments[index] for index in indexes]
    return EvidenceAlignment(
        audio_start=min(segment.start for segment in selected),
        audio_end=max(segment.end for segment in selected),
        segment_indexes=indexes,
        score=round(score, 3),
    )
