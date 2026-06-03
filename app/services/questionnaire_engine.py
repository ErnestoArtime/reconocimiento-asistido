import json
from pathlib import Path
from typing import Any

from app.models.suggestion import AiSuggestion, ValidatedSuggestion
from app.services.text_utils import normalize_text, section_matches


class QuestionnaireEngine:
    def __init__(self, json_path: Path):
        self.path = json_path
        self.data = json.loads(self.path.read_text(encoding="utf-8"))
        self.questions_by_id: dict[str, dict[str, Any]] = {}
        self.sections_by_module: dict[str, list[str]] = {}
        self._index()

    def _index(self) -> None:
        for module_name, module_data in self.data.items():
            sections: set[str] = set()
            for question in module_data.get("questions", []):
                self.questions_by_id[question["id"]] = question
                if question.get("section"):
                    sections.add(question["section"])
            self.sections_by_module[module_name] = sorted(sections, key=normalize_text)

    def get_modules(self) -> list[str]:
        return sorted(self.data.keys())

    def get_sections(self, module: str) -> list[str]:
        self._ensure_module(module)
        return self.sections_by_module[module]

    def get_questions_by_section(self, module: str, section: str) -> list[dict[str, Any]]:
        self._ensure_module(module)
        return [
            question
            for question in self.data[module].get("questions", [])
            if section_matches(question.get("section", ""), section)
        ]

    def get_questions_by_module(self, module: str) -> list[dict[str, Any]]:
        """Todas las preguntas del modulo, sin filtrar por seccion.

        Usado en el flujo de entrevista libre: el medico graba sin ceñirse a
        una seccion, asi que la extraccion corre sobre el modulo completo y cada
        sugerencia se ubica en su pregunta (que ya implica su seccion).
        """
        self._ensure_module(module)
        return list(self.data[module].get("questions", []))

    def get_question(self, question_id: str) -> dict[str, Any] | None:
        return self.questions_by_id.get(question_id)

    def validate_suggestions(self, suggestions: list[AiSuggestion]) -> list[ValidatedSuggestion]:
        valid: list[ValidatedSuggestion] = []

        for suggestion in suggestions:
            question = self.get_question(suggestion.question_id)
            if not question:
                continue

            codes = question.get("codes", {})
            selected_codes = [code for code in suggestion.selected_codes if code in codes]
            question_type = question.get("question_type", "")

            if question_type in {"yesno", "yesnoremember", "choice"}:
                selected_codes = selected_codes[:1]

            selected_labels = [codes[code] for code in selected_codes]
            free_text = suggestion.free_text

            if not selected_codes and not free_text:
                continue

            valid.append(
                ValidatedSuggestion(
                    question_id=suggestion.question_id,
                    selected_codes=selected_codes,
                    selected_labels=selected_labels,
                    free_text=free_text,
                    confidence=suggestion.confidence,
                    evidence=suggestion.evidence,
                    speaker=suggestion.speaker,
                    status=suggestion.status,
                    question_text=question.get("text", ""),
                    question_type=question_type,
                    module=question.get("module", ""),
                    section=question.get("section", ""),
                )
            )

        return valid

    def _ensure_module(self, module: str) -> None:
        if module not in self.data:
            raise KeyError(f"Modulo no encontrado: {module}")

