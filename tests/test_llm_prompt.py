from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.llm_provider import build_system_prompt  # noqa: E402


class LlmPromptTest(unittest.TestCase):
    def test_exam_prompt_allows_doctor_evidence_without_patient_contradiction(self) -> None:
        prompt = build_system_prompt("exam")

        self.assertIn("module=exam", prompt)
        self.assertIn("MEDICO", prompt)
        self.assertIn("No exijas palabras del paciente", prompt)
        self.assertIn("hablante clinicamente relevante", prompt)
        self.assertNotIn("solo si el paciente lo afirma", prompt)
        self.assertNotIn("respuesta del paciente) puede", prompt)

    def test_history_prompt_keeps_doctor_as_context(self) -> None:
        prompt = build_system_prompt("history")

        self.assertIn("module=history", prompt)
        self.assertIn("medico aporta contexto", prompt)
        self.assertIn("PACIENTE aporta la evidencia principal", prompt)


if __name__ == "__main__":
    unittest.main()
