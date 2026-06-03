from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.suggestion import AiSuggestion  # noqa: E402
from app.services.field_extraction_service import (  # noqa: E402
    chunk_questions,
    extract_field,
    extract_small_batches,
)
from app.services.questionnaire_engine import QuestionnaireEngine  # noqa: E402


class FieldExtractionServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = QuestionnaireEngine(ROOT / "app" / "data" / "json_IA.json")
        cls.questions = cls.engine.get_questions_by_section("exam", "CABEZA")

    def test_chunk_questions(self) -> None:
        chunks = chunk_questions(self.questions[:5], 2)

        self.assertEqual([len(chunk) for chunk in chunks], [2, 2, 1])

    def test_extract_field_limits_question_scope(self) -> None:
        boca = next(question for question in self.questions if question["id"] == "E1-3")

        suggestions = extract_field(
            text="La boca esta normal. Oidos normales.",
            module="exam",
            section="CABEZA",
            question=boca,
        )

        self.assertEqual([item.question_id for item in suggestions], ["E1-3"])

    def test_extract_small_batches_merges_without_duplicates(self) -> None:
        calls: list[list[str]] = []

        def fake_extractor(
            _text: str,
            _module: str,
            _section: str,
            questions: list[dict[str, Any]],
        ) -> list[AiSuggestion]:
            calls.append([question["id"] for question in questions])
            first = questions[0]
            return [
                AiSuggestion(
                    question_id=first["id"],
                    selected_codes=[next(iter(first["codes"].keys()))],
                    confidence=0.8,
                    evidence="x",
                )
            ]

        suggestions = extract_small_batches(
            text="x",
            module="exam",
            section="CABEZA",
            questions=self.questions[:5],
            batch_size=2,
            extractor=fake_extractor,
        )

        self.assertEqual([len(call) for call in calls], [2, 2, 1])
        self.assertEqual(len(suggestions), 3)

    def test_parallel_batches_preserve_merge_order(self) -> None:
        # El primer lote tarda mas: si el orden no se preservara, un lote
        # posterior ganaria la fusion. map() mantiene orden de entrada -> el
        # primer lote sigue prevaleciendo.
        import time

        def slow_extractor(
            _text: str,
            _module: str,
            _section: str,
            questions: list[dict[str, Any]],
        ) -> list[AiSuggestion]:
            first = questions[0]
            # Lote que empieza con E1-1 (primer chunk) duerme mas.
            time.sleep(0.15 if first["id"] == self.questions[0]["id"] else 0.0)
            return [
                AiSuggestion(
                    question_id=first["id"],
                    selected_codes=[next(iter(first["codes"].keys()))],
                    confidence=0.8,
                    evidence="x",
                )
            ]

        suggestions = extract_small_batches(
            text="x",
            module="exam",
            section="CABEZA",
            questions=self.questions[:6],
            batch_size=2,
            extractor=slow_extractor,
            max_workers=3,
        )

        ids = [s.question_id for s in suggestions]
        expected_first = self.questions[0]["id"]
        self.assertEqual(ids[0], expected_first, "primer lote debe prevalecer pese a tardar mas")
        self.assertEqual(len(suggestions), 3)

    def test_invalid_batch_size_rejected(self) -> None:
        with self.assertRaises(ValueError):
            chunk_questions(self.questions, 0)


if __name__ == "__main__":
    unittest.main()
