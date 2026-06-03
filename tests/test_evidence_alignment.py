from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.audio.base import Segment  # noqa: E402
from app.services.audio.evidence_alignment import align_evidence_to_segments  # noqa: E402


class EvidenceAlignmentTest(unittest.TestCase):
    def test_exact_match_single_segment(self) -> None:
        segments = [
            Segment(start=0.0, end=1.0, text="Cuero cabelludo normal."),
            Segment(start=1.0, end=2.0, text="La boca esta normal."),
        ]

        alignment = align_evidence_to_segments("boca esta normal", segments)

        self.assertIsNotNone(alignment)
        assert alignment is not None
        self.assertEqual(alignment.audio_start, 1.0)
        self.assertEqual(alignment.audio_end, 2.0)
        self.assertEqual(alignment.segment_indexes, [1])
        self.assertEqual(alignment.score, 1.0)

    def test_exact_match_across_segments(self) -> None:
        segments = [
            Segment(start=0.0, end=1.2, text="El oido no es normal"),
            Segment(start=1.2, end=2.4, text="por tapon de cerumen derecho."),
        ]

        alignment = align_evidence_to_segments(
            "oido no es normal por tapon de cerumen derecho",
            segments,
        )

        self.assertIsNotNone(alignment)
        assert alignment is not None
        self.assertEqual(alignment.audio_start, 0.0)
        self.assertEqual(alignment.audio_end, 2.4)
        self.assertEqual(alignment.segment_indexes, [0, 1])

    def test_fuzzy_match_uses_token_overlap(self) -> None:
        segments = [
            Segment(start=0.0, end=1.0, text="La boca se observa sin hallazgos."),
            Segment(start=1.0, end=2.0, text="Oido derecho con cerumen."),
        ]

        alignment = align_evidence_to_segments(
            "tapon de cerumen derecho",
            segments,
            min_score=0.6,
        )

        self.assertIsNotNone(alignment)
        assert alignment is not None
        self.assertEqual(alignment.segment_indexes, [1])
        self.assertGreaterEqual(alignment.score, 0.6)

    def test_returns_none_when_no_localizable_evidence(self) -> None:
        segments = [
            Segment(start=0.0, end=1.0, text="Cuero cabelludo normal."),
            Segment(start=1.0, end=2.0, text="Cara normal."),
        ]

        alignment = align_evidence_to_segments("consume alcohol", segments)

        self.assertIsNone(alignment)

    def test_empty_input_returns_none(self) -> None:
        self.assertIsNone(align_evidence_to_segments("", []))


if __name__ == "__main__":
    unittest.main()
