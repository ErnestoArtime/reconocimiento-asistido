from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from app.services.text_utils import normalize_text


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES_PATH = ROOT / "app" / "data" / "clinical_negation_es.yaml"

NegationCategory = Literal[
    "negation_pre",
    "negation_post",
    "uncertainty",
    "historical",
    "pseudo_negation",
]


@dataclass(frozen=True)
class NegationFinding:
    category: NegationCategory
    cue: str
    span: str
    temporality: str


def load_negation_rules(path: Path = DEFAULT_RULES_PATH) -> dict[str, list[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return {
        str(category): [str(item) for item in values]
        for category, values in data.items()
        if isinstance(values, list)
    }


def detect_clinical_negation(
    text: str,
    *,
    rules: dict[str, list[str]] | None = None,
) -> list[NegationFinding]:
    """Detecta negacion, incertidumbre y temporalidad historica por reglas simples."""
    active_rules = rules or load_negation_rules()
    normalized = normalize_text(text)
    findings: list[NegationFinding] = []

    pseudo_cues = active_rules.get("pseudo_negation", [])
    pseudo_spans = [
        cue for cue in pseudo_cues if _contains_phrase(normalized, normalize_text(cue))
    ]

    for category in (
        "uncertainty",
        "historical",
        "negation_pre",
        "negation_post",
        "pseudo_negation",
    ):
        for cue in active_rules.get(category, []):
            normalized_cue = normalize_text(cue)
            if not _contains_phrase(normalized, normalized_cue):
                continue
            if category != "pseudo_negation" and _inside_pseudo_negation(
                normalized_cue,
                pseudo_spans,
            ):
                continue
            findings.append(
                NegationFinding(
                    category=category,  # type: ignore[arg-type]
                    cue=cue,
                    span=_span_around(normalized, normalized_cue),
                    temporality=_temporality_for(category),
                )
            )

    return findings


def has_category(findings: list[NegationFinding], category: NegationCategory) -> bool:
    return any(finding.category == category for finding in findings)


def _contains_phrase(text: str, phrase: str) -> bool:
    if not phrase:
        return False
    padded_text = f" {text} "
    padded_phrase = f" {phrase} "
    return padded_phrase in padded_text


def _inside_pseudo_negation(cue: str, pseudo_spans: list[str]) -> bool:
    return any(cue in span for span in pseudo_spans)


def _span_around(text: str, cue: str, window: int = 45) -> str:
    index = text.find(cue)
    if index == -1:
        return cue
    start = max(0, index - window)
    end = min(len(text), index + len(cue) + window)
    return text[start:end].strip()


def _temporality_for(category: str) -> str:
    if category == "historical":
        return "historical"
    if category == "uncertainty":
        return "uncertain"
    return "present"
