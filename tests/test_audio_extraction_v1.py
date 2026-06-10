from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.extraction_contract import SuggestionV1  # noqa: E402
from app.services.audio.base import Segment, TranscriptResult  # noqa: E402
from app.services.audio.extraction_v1 import (  # noqa: E402
    apply_audio_evidence_alignment,
    extraction_text_for_module,
    transcription_meta_v1,
)


class ExtractionTextForModuleTest(unittest.TestCase):
    def _diarized(self) -> TranscriptResult:
        # SPEAKER_00/SPEAKER_01 son clusters, no roles clinicos confirmados.
        return TranscriptResult(
            text="Ha fumado? No, lo deje hace anos.",
            segments=[
                Segment(start=0.0, end=1.5, text="Ha fumado?", speaker="SPEAKER_00"),
                Segment(start=1.5, end=3.0, text="No, lo deje hace anos.", speaker="SPEAKER_01"),
            ],
        )

    def test_history_keeps_all_turns_with_speaker_context(self) -> None:
        out = extraction_text_for_module(self._diarized(), "history")
        self.assertEqual(
            out,
            "[SPEAKER_00|role=unknown] Ha fumado?\n"
            "[SPEAKER_01|role=unknown] No, lo deje hace anos.",
        )

    def test_exam_keeps_all_turns_with_speaker_context(self) -> None:
        out = extraction_text_for_module(self._diarized(), "exam")
        self.assertEqual(
            out,
            "[SPEAKER_00|role=unknown] Ha fumado?\n"
            "[SPEAKER_01|role=unknown] No, lo deje hace anos.",
        )

    def test_no_diarization_returns_full_text(self) -> None:
        tr = TranscriptResult(
            text="texto completo",
            segments=[Segment(start=0.0, end=1.0, text="texto completo")],
        )
        self.assertEqual(extraction_text_for_module(tr, "history"), "texto completo")

    def test_empty_filter_falls_back_to_full(self) -> None:
        tr = TranscriptResult(
            text="Ha fumado?",
            segments=[Segment(start=0.0, end=1.0, text="Ha fumado?", speaker="SPEAKER_00")],
        )
        self.assertEqual(
            extraction_text_for_module(tr, "history"),
            "[SPEAKER_00|role=unknown] Ha fumado?",
        )


class AudioExtractionV1Test(unittest.TestCase):
    def test_apply_audio_evidence_alignment_sets_timestamps(self) -> None:
        transcription = TranscriptResult(
            text="La boca esta normal.",
            segments=[Segment(start=3.0, end=4.5, text="La boca esta normal.")],
        )
        suggestions = [
            SuggestionV1(
                question_id="E1-3",
                selected_codes=["E1-31"],
                confidence=0.8,
                evidence="boca esta normal",
            )
        ]

        [aligned] = apply_audio_evidence_alignment(suggestions, transcription)

        self.assertEqual(aligned.audio_start, 3.0)
        self.assertEqual(aligned.audio_end, 4.5)
        self.assertNotIn("no_audio_timestamp", aligned.risk_flags)

    def test_apply_audio_evidence_alignment_flags_missing_timestamp(self) -> None:
        transcription = TranscriptResult(
            text="La boca esta normal.",
            segments=[Segment(start=3.0, end=4.5, text="La boca esta normal.")],
        )
        suggestions = [
            SuggestionV1(
                question_id="C5-2",
                selected_codes=["C5-22"],
                confidence=0.8,
                evidence="no consume alcohol",
            )
        ]

        [aligned] = apply_audio_evidence_alignment(suggestions, transcription)

        self.assertIsNone(aligned.audio_start)
        self.assertIsNone(aligned.audio_end)
        self.assertIn("no_audio_timestamp", aligned.risk_flags)

    def test_transcription_meta_detects_diarization(self) -> None:
        transcription = TranscriptResult(
            text="No fuma.",
            language="es",
            duration_s=2.5,
            rtf=0.4,
            provider="faster_whisper",
            model="medium",
            segments=[Segment(start=0.0, end=2.5, text="No fuma.", speaker="paciente")],
        )

        meta = transcription_meta_v1(transcription)

        self.assertEqual(meta.provider, "faster_whisper")
        self.assertEqual(meta.model, "medium")
        self.assertTrue(meta.diarized)

    def test_speaker_propagated_when_segment_has_consensus(self) -> None:
        """Si todos los segmentos alineados tienen mismo speaker → propagar."""
        transcription = TranscriptResult(
            text="No fuma. Nunca ha fumado.",
            segments=[
                Segment(start=0.0, end=2.0, text="No fuma.", speaker="paciente"),
                Segment(start=2.0, end=4.0, text="Nunca ha fumado.", speaker="paciente"),
            ],
        )
        suggestions = [
            SuggestionV1(
                question_id="C5-1",
                selected_codes=["C5-12"],
                confidence=0.9,
                evidence="No fuma",
            ),
        ]
        [aligned] = apply_audio_evidence_alignment(suggestions, transcription)
        self.assertEqual(aligned.speaker, "paciente")

    def test_speaker_cluster_propagates_as_unknown(self) -> None:
        """SPEAKER_00 es cluster de diarizacion, no rol medico confirmado."""
        transcription = TranscriptResult(
            text="Exploracion boca normal.",
            segments=[
                Segment(start=0.0, end=2.0, text="Exploracion boca normal.", speaker="SPEAKER_00"),
            ],
        )
        suggestions = [
            SuggestionV1(
                question_id="E1-3",
                selected_codes=["E1-31"],
                confidence=0.9,
                evidence="boca normal",
            ),
        ]
        [aligned] = apply_audio_evidence_alignment(suggestions, transcription)
        self.assertEqual(aligned.speaker, "unknown")

    def test_speaker_not_propagated_when_mixed(self) -> None:
        """Ventana con dos speakers distintos → no propagar (consensus fails)."""
        transcription = TranscriptResult(
            text="No fuma. Hace dos anos que no.",
            segments=[
                Segment(start=0.0, end=1.0, text="No fuma.", speaker="paciente"),
                Segment(start=1.0, end=3.0, text="Hace dos anos que no.", speaker="medico"),
            ],
        )
        suggestions = [
            SuggestionV1(
                question_id="C5-1",
                selected_codes=["C5-12"],
                confidence=0.9,
                evidence="No fuma Hace dos anos que no",  # cubre ambos
            ),
        ]
        [aligned] = apply_audio_evidence_alignment(suggestions, transcription)
        self.assertIsNone(aligned.speaker)

    def test_existing_speaker_not_overwritten(self) -> None:
        """Si suggestion ya trae speaker, NO se sobrescribe por el alineador."""
        transcription = TranscriptResult(
            text="No fuma.",
            segments=[
                Segment(start=0.0, end=2.0, text="No fuma.", speaker="medico"),
            ],
        )
        suggestions = [
            SuggestionV1(
                question_id="C5-1",
                selected_codes=["C5-12"],
                confidence=0.9,
                evidence="No fuma",
                speaker="paciente",  # ya viene de otra fuente
            ),
        ]
        [aligned] = apply_audio_evidence_alignment(suggestions, transcription)
        self.assertEqual(aligned.speaker, "paciente")  # NO sobreescrito

    def test_no_speaker_no_propagation(self) -> None:
        """Segmentos sin speaker (no diarizado) no afectan speaker de suggestion."""
        transcription = TranscriptResult(
            text="No fuma.",
            segments=[
                Segment(start=0.0, end=2.0, text="No fuma.", speaker=None),
            ],
        )
        suggestions = [
            SuggestionV1(
                question_id="C5-1",
                selected_codes=["C5-12"],
                confidence=0.9,
                evidence="No fuma",
            ),
        ]
        [aligned] = apply_audio_evidence_alignment(suggestions, transcription)
        self.assertIsNone(aligned.speaker)


if __name__ == "__main__":
    unittest.main()
