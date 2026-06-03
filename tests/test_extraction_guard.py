from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api import deps  # noqa: E402
from app.main import app  # noqa: E402
from app.models.suggestion import AiSuggestion  # noqa: E402
from app.services.extraction_guard import (  # noqa: E402
    MAX_LLM_CONFIDENCE,
    ground_and_filter_llm,
    narrow_questions_by_relevance,
)

EXAM_QUESTIONS = [
    {
        "id": "E1-1",
        "text": "La inspeccion de cuero cabelludo es normal?",
        "question_type": "yesno",
        "codes": {"E1-11": "Si", "E1-12": "No"},
    },
    {
        "id": "E1-3",
        "text": "La exploracion de la boca es normal?",
        "question_type": "yesno",
        "codes": {"E1-31": "Si", "E1-32": "No"},
    },
]

SMOKING_QUESTION = {
    "id": "H1-1",
    "text": "Fuma actualmente?",
    "question_type": "yesno",
    "codes": {"H1-11": "Si", "H1-12": "No"},
}


class ExtractionGuardUnitTest(unittest.TestCase):
    def test_drops_irrelevant_evidence(self) -> None:
        transcript = "El paciente refiere que no fuma actualmente. No bebe alcohol."
        hallucinated = [
            AiSuggestion(
                question_id=q["id"],
                selected_codes=[next(iter(q["codes"]))],
                confidence=1.0,
                evidence="El paciente refiere que no fuma actualmente.",
            )
            for q in EXAM_QUESTIONS
        ]
        kept = ground_and_filter_llm(hallucinated, EXAM_QUESTIONS, transcript)
        self.assertEqual(kept, [], "evidencia de tabaco no aplica a preguntas de exam")

    def test_drops_ungrounded_evidence(self) -> None:
        transcript = "Fuma medio paquete al dia."
        sugg = [
            AiSuggestion(
                question_id="H1-1",
                selected_codes=["H1-11"],
                confidence=0.9,
                evidence="texto que no esta en la transcripcion",
            )
        ]
        kept = ground_and_filter_llm(sugg, [SMOKING_QUESTION], transcript)
        self.assertEqual(kept, [])

    def test_keeps_relevant_and_caps_confidence(self) -> None:
        transcript = "El paciente fuma actualmente medio paquete al dia."
        sugg = [
            AiSuggestion(
                question_id="H1-1",
                selected_codes=["H1-11"],
                confidence=1.0,
                evidence="El paciente fuma actualmente",
            )
        ]
        kept = ground_and_filter_llm(sugg, [SMOKING_QUESTION], transcript)
        self.assertEqual(len(kept), 1)
        self.assertLessEqual(kept[0].confidence, MAX_LLM_CONFIDENCE)


class GuardCalibrationTest(unittest.TestCase):
    """Audios con preguntas reformuladas: respuestas sin la palabra-tema.

    El paciente responde 'lo deje hace tres anos' a una pregunta de tabaco.
    La cita no contiene 'fuma'; con scope=evidence se descartaba. Con scope
    transcript (default) y fuzzy grounding se conserva.
    """

    def test_transcript_scope_keeps_answer_without_keyword(self) -> None:
        transcript = "Antes fumaba pero lo deje hace tres anos."
        sugg = [
            AiSuggestion(
                question_id="H1-1",
                selected_codes=["H1-12"],
                confidence=0.8,
                evidence="lo deje hace tres anos",
            )
        ]
        kept = ground_and_filter_llm([s.model_copy() for s in sugg], [SMOKING_QUESTION], transcript)
        self.assertEqual(len(kept), 1, "scope=transcript conserva respuesta sin palabra-tema")

        dropped = ground_and_filter_llm(
            [s.model_copy() for s in sugg],
            [SMOKING_QUESTION],
            transcript,
            relevance_scope="evidence",
        )
        self.assertEqual(dropped, [], "scope=evidence (legacy) la descarta")

    def test_fuzzy_grounding_tolerates_minor_rewrite(self) -> None:
        transcript = "El paciente fuma medio paquete al dia."
        sugg = [
            AiSuggestion(
                question_id="H1-1",
                selected_codes=["H1-11"],
                confidence=0.7,
                evidence="paciente fuma medio paquete dia",  # falta 'el', 'al'
            )
        ]
        kept = ground_and_filter_llm(
            [s.model_copy() for s in sugg], [SMOKING_QUESTION], transcript, fuzzy_grounding=True
        )
        self.assertEqual(len(kept), 1, "fuzzy ancla por cobertura de tokens")

        strict = ground_and_filter_llm(
            [s.model_copy() for s in sugg], [SMOKING_QUESTION], transcript, fuzzy_grounding=False
        )
        self.assertEqual(strict, [], "sin fuzzy exige subcadena literal")

    def test_lenient_mode_skips_relevance(self) -> None:
        transcript = "El paciente menciona algo no relacionado."
        sugg = [
            AiSuggestion(
                question_id="H1-1",
                selected_codes=["H1-12"],
                confidence=0.6,
                evidence="El paciente menciona algo no relacionado",
            )
        ]
        kept = ground_and_filter_llm(
            [s.model_copy() for s in sugg], [SMOKING_QUESTION], transcript, lenient=True
        )
        self.assertEqual(len(kept), 1, "lenient solo exige anclaje, no relevancia")

        normal = ground_and_filter_llm(
            [s.model_copy() for s in sugg], [SMOKING_QUESTION], transcript, lenient=False
        )
        self.assertEqual(normal, [], "modo normal descarta tema ausente del transcript")


class NarrowQuestionsTest(unittest.TestCase):
    def test_narrows_module_to_topical_questions(self) -> None:
        questions = EXAM_QUESTIONS + [SMOKING_QUESTION]
        text = "El paciente no fuma actualmente. No bebe alcohol."
        narrowed = narrow_questions_by_relevance(questions, text)
        ids = {q["id"] for q in narrowed}
        self.assertIn("H1-1", ids, "pregunta de tabaco debe quedar")
        self.assertNotIn("E1-1", ids, "cuero cabelludo no aplica al texto")

    def test_empty_text_keeps_all(self) -> None:
        questions = EXAM_QUESTIONS + [SMOKING_QUESTION]
        self.assertEqual(len(narrow_questions_by_relevance(questions, "")), 3)


class _FakeHallucinatingOllama:
    """Simula modelo que rellena TODA pregunta con Si + evidencia copiada."""

    def __init__(self, model: str) -> None:
        self.model = model

    def with_model(self, model: str) -> "_FakeHallucinatingOllama":
        return _FakeHallucinatingOllama(model)

    def extract(self, text, module, section, questions):
        first_sentence = (text.split(".")[0] + ".").strip()
        return [
            AiSuggestion(
                question_id=q["id"],
                selected_codes=[next(iter(q.get("codes", {})), "")],
                confidence=1.0,
                evidence=first_sentence,
            )
            for q in questions
            if q.get("codes")
        ]


class ExtractionGuardApiTest(unittest.TestCase):
    def setUp(self) -> None:
        from app.core.config import get_settings

        model = get_settings().ollama_model
        app.dependency_overrides[deps.get_ollama_provider] = (
            lambda: _FakeHallucinatingOllama(model)
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(deps.get_ollama_provider, None)

    def test_hallucinated_exam_extraction_is_filtered(self) -> None:
        resp = self.client.post(
            "/api/v1/ia/extract-from-text",
            json={
                "module": "exam",
                "text": (
                    "El paciente refiere que no fuma actualmente. "
                    "Dejo de fumar hace tres anos. No consume alcohol."
                ),
                "ia_provider": "ollama",
            },
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(
            payload["suggestions"],
            [],
            "la guardia debe descartar las sugerencias alucinadas de exam",
        )


if __name__ == "__main__":
    unittest.main()
