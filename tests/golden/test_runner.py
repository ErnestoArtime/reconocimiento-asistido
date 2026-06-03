from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.questionnaire_engine import QuestionnaireEngine  # noqa: E402


GOLDEN_ROOT = Path(__file__).resolve().parent


def load_cases() -> list[tuple[Path, dict[str, Any]]]:
    cases: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(GOLDEN_ROOT.rglob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        cases.append((path, data))
    return cases


class GoldenSetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = QuestionnaireEngine(ROOT / "app" / "data" / "json_IA.json")

    def test_cases_have_valid_shape_and_codes(self) -> None:
        cases = load_cases()
        self.assertGreaterEqual(len(cases), 10)

        for path, case in cases:
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertIn(case.get("module"), {"history", "exam"})
                self.assertIsInstance(case.get("section"), str)
                self.assertTrue(case.get("transcript", "").strip())
                expected = case.get("expected_suggestions")
                self.assertIsInstance(expected, list)
                self.assertGreater(len(expected), 0)

                questions = {
                    q["id"]: q
                    for q in self.engine.get_questions_by_section(
                        case["module"], case["section"]
                    )
                }
                question_order = list(questions.keys())
                section_entry = (
                    self.engine.data[case["module"]].get("entry_question_id")
                    if self.engine.data[case["module"]].get("entry_question_id")
                    in questions
                    else question_order[0]
                )
                expected_by_id = {
                    item.get("question_id"): item for item in expected
                }
                expected_missing = set(case.get("expected_missing", []))

                for item in expected:
                    question_id = item.get("question_id")
                    self.assertIn(question_id, questions)
                    self.assertIsInstance(item.get("selected_codes"), list)
                    codes = questions[question_id].get("codes", {})
                    for code in item["selected_codes"]:
                        self.assertIn(code, codes)
                    self.assertTrue(item.get("evidence_contains", "").strip())

                for question_id in case.get("expected_missing", []):
                    self.assertIn(question_id, questions)

                graph_path = case.get("expected_graph_path")
                self.assertIsInstance(graph_path, list)
                self.assertGreater(len(graph_path), 0)
                self.assertEqual(graph_path[0], section_entry)

                path_set = set(graph_path)
                for question_id in graph_path:
                    self.assertIn(question_id, questions)
                    self.assertTrue(
                        question_id in expected_by_id
                        or question_id in expected_missing,
                        f"{question_id} appears in expected_graph_path but is not answered or marked missing",
                    )

                for question_id in expected_by_id:
                    self.assertIn(
                        question_id,
                        path_set,
                        f"{question_id} has an expected suggestion but is absent from expected_graph_path",
                    )
                for question_id in expected_missing:
                    self.assertIn(
                        question_id,
                        path_set,
                        f"{question_id} is marked missing but is absent from expected_graph_path",
                    )

                for current_id, next_id in zip(graph_path, graph_path[1:]):
                    current_answer = expected_by_id.get(current_id)
                    if not current_answer:
                        continue
                    transitions = questions[current_id].get("transitions", {})
                    for code in current_answer["selected_codes"]:
                        transition_target = transitions.get(code)
                        if transition_target in questions:
                            self.assertEqual(
                                transition_target,
                                next_id,
                                f"{current_id} with {code} should transition to {transition_target}, not {next_id}",
                            )

                all_codes = {
                    code
                    for question in questions.values()
                    for code in question.get("codes", {}).keys()
                }
                for code in case.get("forbidden_codes", []):
                    self.assertIn(code, all_codes)


if __name__ == "__main__":
    unittest.main()
