from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.extraction_contract import SuggestionV1  # noqa: E402
from app.services.graph_mapping_engine import build_graph_report  # noqa: E402
from app.services.questionnaire_engine import QuestionnaireEngine  # noqa: E402


class GraphMappingEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = QuestionnaireEngine(ROOT / "app" / "data" / "json_IA.json")

    def questions(self, module: str, section: str) -> list[dict]:
        return self.engine.get_questions_by_section(module, section)

    def test_exam_cabeza_normal_path(self) -> None:
        suggestions = [
            SuggestionV1(question_id="E1-1", selected_codes=["E1-11"], confidence=0.9, evidence="x"),
            SuggestionV1(question_id="E1-2", selected_codes=["E1-21"], confidence=0.9, evidence="x"),
            SuggestionV1(question_id="E1-3", selected_codes=["E1-31"], confidence=0.9, evidence="x"),
            SuggestionV1(question_id="E1-4", selected_codes=["E1-41"], confidence=0.9, evidence="x"),
            SuggestionV1(question_id="E1-5", selected_codes=["E1-51"], confidence=0.9, evidence="x"),
            SuggestionV1(question_id="E1-6", selected_codes=["E1-61"], confidence=0.9, evidence="x"),
        ]

        report = build_graph_report(
            module_entry_question_id=self.engine.data["exam"].get("entry_question_id"),
            questions=self.questions("exam", "CABEZA"),
            suggestions=suggestions,
        )

        self.assertEqual(report.entry_question_id, "E1-1")
        self.assertEqual(report.path, ["E1-1", "E1-2", "E1-3", "E1-4", "E1-5", "E1-6"])
        self.assertEqual(report.accepted_question_ids, report.path)
        self.assertEqual(report.missing_required, [])
        self.assertEqual(report.discarded, [])

    def test_missing_unambiguous_question_continues_path(self) -> None:
        suggestions = [
            SuggestionV1(question_id="C5-1", selected_codes=["C5-12"], confidence=0.9, evidence="x"),
            SuggestionV1(question_id="C5-121", selected_codes=["C5-1212"], confidence=0.9, evidence="x"),
            SuggestionV1(question_id="C5-2", selected_codes=["C5-22"], confidence=0.9, evidence="x"),
            SuggestionV1(question_id="C5-3", selected_codes=["C5-32"], confidence=0.9, evidence="x"),
        ]

        report = build_graph_report(
            module_entry_question_id=self.engine.data["history"].get("entry_question_id"),
            questions=self.questions("history", "HABITOS"),
            suggestions=suggestions,
        )

        self.assertEqual(report.entry_question_id, "C5-1")
        self.assertEqual(
            report.path,
            ["C5-1", "C5-121", "C5-2", "C5-221", "C5-3", "C5-321"],
        )
        self.assertEqual(report.missing_required, ["C5-221", "C5-321"])
        self.assertEqual(report.discarded, [])

    def test_off_path_suggestion_is_discarded(self) -> None:
        suggestions = [
            SuggestionV1(question_id="C5-1", selected_codes=["C5-12"], confidence=0.9, evidence="x"),
            SuggestionV1(question_id="C5-131", selected_codes=["C5-1313"], confidence=0.9, evidence="x"),
        ]

        report = build_graph_report(
            module_entry_question_id=self.engine.data["history"].get("entry_question_id"),
            questions=self.questions("history", "HABITOS"),
            suggestions=suggestions,
        )

        self.assertEqual(report.path, ["C5-1", "C5-121", "C5-2"])
        self.assertEqual(report.missing_required, ["C5-121", "C5-2"])
        self.assertEqual(
            report.discarded,
            [{"question_id": "C5-131", "reason": "not_reachable_from_selected_path"}],
        )


if __name__ == "__main__":
    unittest.main()
