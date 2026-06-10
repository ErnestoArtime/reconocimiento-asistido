from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.question_family_builder import (  # noqa: E402
    chunk_questions_by_family,
    enrich_questions_with_ai_context,
    expand_with_family_context,
)


def _q(
    question_id: str,
    text: str,
    *,
    section: str = "TEST",
    question_type: str = "yesno",
    transitions: dict[str, str] | None = None,
) -> dict:
    return {
        "id": question_id,
        "module": "history",
        "section": section,
        "text": text,
        "question_type": question_type,
        "codes": {f"{question_id}-1": "Si", f"{question_id}-2": "No"},
        "transitions": transitions or {},
    }


class QuestionFamilyBuilderTest(unittest.TestCase):
    def test_enriches_parent_child_dependency(self) -> None:
        questions = [
            _q("B1-1", "Tiene su padre alguna enfermedad?", transitions={"B1-11": "B1-121", "B1-12": "B1-2"}),
            _q("B1-121", "Que enfermedades ha tenido?", question_type="free"),
            _q("B1-2", "Tiene su madre alguna enfermedad?"),
        ]

        enriched = {q["id"]: q for q in enrich_questions_with_ai_context(questions)}

        self.assertEqual(enriched["B1-121"]["parent_question_id"], "B1-1")
        self.assertEqual(enriched["B1-121"]["required_parent_codes"], ["B1-11"])
        self.assertEqual(enriched["B1-121"]["subject"], "father")
        self.assertEqual(enriched["B1-121"]["temporal_scope"], "ever")

    def test_selecting_child_keeps_parent(self) -> None:
        questions = [
            _q("B1-1", "Tiene su padre alguna enfermedad?", transitions={"B1-11": "B1-121", "B1-12": "B1-2"}),
            _q("B1-121", "Que enfermedades ha tenido?", question_type="free"),
            _q("B1-2", "Tiene su madre alguna enfermedad?"),
        ]

        expanded = expand_with_family_context(questions, [questions[1]])

        self.assertEqual([q["id"] for q in expanded], ["B1-1", "B1-121"])

    def test_selecting_parent_keeps_children(self) -> None:
        questions = [
            _q("A1-3", "Esta expuesto a riesgos?", transitions={"A1-31": "A1-321", "A1-32": "A1-4"}),
            _q("A1-321", "A que riesgo esta expuesto?"),
            _q("A1-4", "Utiliza equipos de proteccion?"),
        ]

        expanded = expand_with_family_context(questions, [questions[0]])

        self.assertEqual([q["id"] for q in expanded], ["A1-3", "A1-321"])

    def test_parent_and_child_stay_in_same_batch(self) -> None:
        questions = [
            _q("B1-1", "Tiene su padre alguna enfermedad?", transitions={"B1-11": "B1-121", "B1-12": "B1-2"}),
            _q("B1-121", "Que enfermedades ha tenido?", question_type="free"),
            _q("B1-2", "Tiene su madre alguna enfermedad?", transitions={"B1-21": "B1-221", "B1-22": "B1-3"}),
            _q("B1-221", "Que enfermedades ha tenido?", question_type="free"),
        ]

        batches = chunk_questions_by_family(questions, batch_size=2)

        self.assertEqual([[q["id"] for q in batch] for batch in batches], [["B1-1", "B1-121"], ["B1-2", "B1-221"]])

    def test_temporal_scope_uses_specific_markers_before_words(self) -> None:
        questions = [
            _q("C5-1", "Fuma?"),
            _q("C5-121", "Ha fumado anteriormente?"),
            _q("C6-121", "Ha consumido anteriormente?"),
            _q("C1-1", "Ha tenido alguna enfermedad?"),
            _q("G1-1", "Toma alguna medicacion?"),
        ]

        enriched = {q["id"]: q for q in enrich_questions_with_ai_context(questions)}

        self.assertEqual(enriched["C5-1"]["temporal_scope"], "current")
        self.assertEqual(enriched["C5-121"]["temporal_scope"], "past")
        self.assertEqual(enriched["C6-121"]["temporal_scope"], "past")
        self.assertEqual(enriched["C1-1"]["temporal_scope"], "ever")
        self.assertEqual(enriched["G1-1"]["temporal_scope"], "current")

    def test_detail_like_variants_are_detected(self) -> None:
        questions = [
            _q("P1", "Tiene sintomas?", transitions={"P1-1": "P1-D", "P1-2": "P2"}),
            _q("P1-D", "Desde cuando?"),
            _q("P2", "Otra pregunta?"),
        ]

        enriched = {q["id"]: q for q in enrich_questions_with_ai_context(questions)}

        self.assertEqual(enriched["P1-D"]["parent_question_id"], "P1")

    def test_family_larger_than_batch_size_is_not_split(self) -> None:
        questions = [
            _q(
                "P1",
                "Tiene hallazgos?",
                transitions={"P1-1": "P1-D1", "P1-2": "P2", "P1-3": "P1-D2"},
            ),
            _q("P1-D1", "Que se detecta?"),
            _q("P1-D2", "Desde cuando?"),
            _q("P2", "Otra pregunta?"),
        ]

        batches = chunk_questions_by_family(questions, batch_size=2)

        self.assertEqual([q["id"] for q in batches[0]], ["P1", "P1-D1", "P1-D2"])


if __name__ == "__main__":
    unittest.main()
