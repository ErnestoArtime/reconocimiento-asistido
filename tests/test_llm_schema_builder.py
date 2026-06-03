from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.llm_provider import build_extraction_schema  # noqa: E402
from app.services.questionnaire_engine import QuestionnaireEngine  # noqa: E402


class LlmSchemaBuilderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = QuestionnaireEngine(ROOT / "app" / "data" / "json_IA.json")

    def test_schema_restricts_question_ids_and_codes(self) -> None:
        questions = self.engine.get_questions_by_section("exam", "CABEZA")[:2]

        schema = build_extraction_schema(questions)

        self.assertEqual(schema["type"], "object")
        self.assertFalse(schema["additionalProperties"])
        variants = schema["properties"]["suggestions"]["items"]["anyOf"]
        self.assertEqual(len(variants), 2)
        self.assertEqual(variants[0]["properties"]["question_id"]["const"], "E1-1")
        self.assertEqual(
            set(variants[0]["properties"]["selected_codes"]["items"]["enum"]),
            {"E1-11", "E1-12"},
        )

    def test_schema_forbids_extra_properties_in_suggestions(self) -> None:
        questions = self.engine.get_questions_by_section("history", "HABITOS")[:1]

        schema = build_extraction_schema(questions)
        variant = schema["properties"]["suggestions"]["items"]["anyOf"][0]

        self.assertFalse(variant["additionalProperties"])
        self.assertIn("question_id", variant["required"])
        self.assertIn("selected_codes", variant["required"])
        self.assertIn("evidence", variant["required"])

    def test_empty_questions_returns_unsatisfiable_item_schema(self) -> None:
        schema = build_extraction_schema([])

        self.assertEqual(
            schema["properties"]["suggestions"]["items"],
            {"anyOf": [{"not": {}}]},
        )


if __name__ == "__main__":
    unittest.main()
