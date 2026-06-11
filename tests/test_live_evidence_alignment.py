import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api.routes_audio import _apply_turn_evidence_metadata
from app.models.extraction_contract import SuggestionV1


class LiveEvidenceAlignmentTests(unittest.TestCase):
    def _suggestion(self, evidence: str, turn_ids: list[str] | None = None) -> SuggestionV1:
        return SuggestionV1(
            question_id="H1",
            module="history",
            section="Historia",
            question_text="Pregunta",
            question_type="yesno",
            selected_codes=["1"],
            selected_labels=["Si"],
            confidence=0.8,
            evidence=evidence,
            evidence_turn_ids=turn_ids or [],
            audio_start=1.0,
            audio_end=2.0,
            speaker_cluster="SPEAKER_FAKE",
        )

    def test_ambiguous_short_evidence_clears_audio_metadata(self) -> None:
        turns = (
            {"turn_id": "live-a-turn-0001", "text": "No.", "start": 0.0, "end": 0.5},
            {"turn_id": "live-a-turn-0002", "text": "No toma medicacion.", "start": 4.0, "end": 5.0},
        )

        result = _apply_turn_evidence_metadata([self._suggestion("No")], turns)[0]

        self.assertEqual(result.evidence_turn_ids, [])
        self.assertIsNone(result.audio_start)
        self.assertIsNone(result.audio_end)
        self.assertIsNone(result.speaker_cluster)

    def test_invalid_llm_turn_id_is_not_preserved(self) -> None:
        turns = (
            {"turn_id": "live-a-turn-0001", "text": "Refiere dolor lumbar.", "start": 2.0, "end": 3.0},
        )

        result = _apply_turn_evidence_metadata(
            [self._suggestion("dolor cervical", ["turno-inexistente"])],
            turns,
        )[0]

        self.assertEqual(result.evidence_turn_ids, [])
        self.assertIsNone(result.audio_start)
        self.assertIsNone(result.audio_end)
        self.assertIsNone(result.speaker_cluster)

    def test_valid_proposed_turn_id_is_used(self) -> None:
        turns = (
            {"turn_id": "live-a-turn-0001", "text": "Sin hallazgos.", "start": 0.0, "end": 1.0},
            {"turn_id": "live-a-turn-0002", "text": "Refiere dolor lumbar.", "start": 2.0, "end": 3.0},
        )

        result = _apply_turn_evidence_metadata(
            [self._suggestion("dolor lumbar", ["live-a-turn-0002"])],
            turns,
        )[0]

        self.assertEqual(result.evidence_turn_ids, ["live-a-turn-0002"])
        self.assertEqual(result.audio_start, 2.0)
        self.assertEqual(result.audio_end, 3.0)


if __name__ == "__main__":
    unittest.main()
