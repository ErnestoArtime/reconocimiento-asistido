from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.llm_provider import _build_user_prompt, build_system_prompt  # noqa: E402


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

    def test_user_prompt_includes_structured_turns_and_turn_ids(self) -> None:
        prompt = _build_user_prompt(
            text="[SPEAKER_00|role=unknown] Fuma?\n[SPEAKER_01|role=unknown] No.",
            module="history",
            section="HABITOS",
            questions=[
                {
                    "id": "C5-1",
                    "text": "Fuma?",
                    "question_type": "yesno",
                    "codes": {"C5-11": "Si", "C5-12": "No"},
                }
            ],
            transcript_turns=[
                {
                    "turn_id": "t1",
                    "speaker_cluster": "SPEAKER_00",
                    "speaker_role": "unknown",
                    "text": "Fuma?",
                },
                {
                    "turn_id": "t2",
                    "speaker_cluster": "SPEAKER_01",
                    "speaker_role": "unknown",
                    "text": "No.",
                },
            ],
        )

        self.assertIn('"transcript_turns"', prompt)
        self.assertIn('"evidence_turn_ids"', prompt)
        self.assertIn('"speaker_cluster"', prompt)
        self.assertIn('"turn_id": "t2"', prompt)


if __name__ == "__main__":
    unittest.main()
