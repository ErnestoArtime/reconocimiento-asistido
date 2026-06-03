from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.audio.base import Segment  # noqa: E402
from app.services.audio.providers.whisperx_provider import map_speakers_to_roles  # noqa: E402


class WhisperXSpeakerMappingTest(unittest.TestCase):
    def test_speaker_with_more_questions_maps_to_medico(self) -> None:
        segments = [
            Segment(start=0.0, end=1.0, text="Fuma actualmente?", speaker="SPEAKER_00"),
            Segment(start=1.0, end=2.0, text="No fuma.", speaker="SPEAKER_01"),
            Segment(start=2.0, end=3.0, text="Consume alcohol?", speaker="SPEAKER_00"),
        ]

        mapped = map_speakers_to_roles(segments)

        self.assertEqual(mapped[0].speaker, "medico")
        self.assertEqual(mapped[1].speaker, "paciente")
        self.assertEqual(mapped[2].speaker, "medico")

    def test_no_question_markers_keeps_original_speakers(self) -> None:
        segments = [
            Segment(start=0.0, end=1.0, text="Boca normal.", speaker="SPEAKER_00"),
            Segment(start=1.0, end=2.0, text="Oidos normales.", speaker="SPEAKER_01"),
        ]

        mapped = map_speakers_to_roles(segments)

        self.assertEqual(
            [segment.speaker for segment in mapped],
            ["SPEAKER_00", "SPEAKER_01"],
        )

    def test_segments_without_speaker_are_preserved(self) -> None:
        segments = [
            Segment(start=0.0, end=1.0, text="Fuma?", speaker="SPEAKER_00"),
            Segment(start=1.0, end=2.0, text="No fuma.", speaker=None),
        ]

        mapped = map_speakers_to_roles(segments)

        self.assertEqual(mapped[0].speaker, "medico")
        self.assertIsNone(mapped[1].speaker)


if __name__ == "__main__":
    unittest.main()
