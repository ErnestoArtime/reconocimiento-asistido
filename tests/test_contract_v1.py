"""Tests del contrato v1 + adaptador legacy."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.extraction_contract import (  # noqa: E402
    SCHEMA_VERSION,
    ExtractionResponseV1,
    GraphReportV1,
    QualityReportV1,
    SuggestionV1,
    TranscriptionMetaV1,
)
from app.models.legacy_adapter import (  # noqa: E402
    build_quality_report,
    legacy_to_v1,
    v1_to_legacy,
)
from app.models.suggestion import AiSuggestion, ValidatedSuggestion  # noqa: E402


class ContractV1Test(unittest.TestCase):
    def test_schema_version_constant(self) -> None:
        self.assertTrue(SCHEMA_VERSION.startswith("2026-"))
        self.assertIn("v1", SCHEMA_VERSION)

    def test_suggestion_minimal_serializes(self) -> None:
        s = SuggestionV1(
            question_id="E1-3",
            selected_codes=["E1-32"],
            confidence=0.85,
            evidence="boca no es normal",
            evidence_turn_ids=["t2"],
            speaker_cluster="SPEAKER_01",
        )
        payload = json.loads(s.model_dump_json())
        self.assertEqual(payload["question_id"], "E1-3")
        self.assertEqual(payload["evidence_turn_ids"], ["t2"])
        self.assertEqual(payload["speaker_cluster"], "SPEAKER_01")
        self.assertEqual(payload["technical_status"], "valid")
        self.assertEqual(payload["review_status"], "pending")
        self.assertEqual(payload["risk_flags"], [])
        self.assertIsNone(payload["audio_start"])

    def test_response_has_default_reports(self) -> None:
        r = ExtractionResponseV1(module="exam", section="CABEZA")
        self.assertEqual(r.schema_version, SCHEMA_VERSION)
        self.assertIsInstance(r.graph_report, GraphReportV1)
        self.assertIsInstance(r.quality_report, QualityReportV1)
        self.assertIsNone(r.transcription)

    def test_response_with_transcription(self) -> None:
        r = ExtractionResponseV1(
            module="history",
            section="HABITOS",
            transcription=TranscriptionMetaV1(
                text="el paciente no fuma",
                duration_s=4.2,
                rtf=0.5,
                provider="faster_whisper",
                model="medium",
            ),
        )
        self.assertEqual(r.transcription.provider, "faster_whisper")

    def test_confidence_bounds_rejected(self) -> None:
        with self.assertRaises(Exception):
            SuggestionV1(question_id="X", confidence=1.5, evidence="x")
        with self.assertRaises(Exception):
            SuggestionV1(question_id="X", confidence=-0.1, evidence="x")

    def test_audio_start_must_be_non_negative(self) -> None:
        with self.assertRaises(Exception):
            SuggestionV1(
                question_id="X",
                confidence=0.5,
                evidence="x",
                audio_start=-1.0,
            )

    def test_extra_fields_forbidden(self) -> None:
        with self.assertRaises(Exception):
            SuggestionV1(
                question_id="X",
                confidence=0.5,
                evidence="x",
                random_field="boom",
            )


class LegacyAdapterTest(unittest.TestCase):
    def test_legacy_to_v1_basic(self) -> None:
        legacy = AiSuggestion(
            question_id="C5-1",
            selected_codes=["C5-12"],
            confidence=0.9,
            evidence="no fuma",
            evidence_turn_ids=["t1"],
            speaker_cluster="SPEAKER_01",
        )
        v1 = legacy_to_v1(legacy)
        self.assertEqual(v1.question_id, "C5-1")
        self.assertEqual(v1.evidence_turn_ids, ["t1"])
        self.assertEqual(v1.speaker_cluster, "SPEAKER_01")
        self.assertEqual(v1.technical_status, "valid")
        self.assertEqual(v1.review_status, "pending")
        self.assertEqual(v1.risk_flags, [])
        self.assertIsNone(v1.audio_start)

    def test_legacy_low_confidence_maps_to_risk_flag(self) -> None:
        legacy = AiSuggestion(
            question_id="C5-1",
            selected_codes=["C5-12"],
            confidence=0.4,
            evidence="no fuma",
            status="low_confidence",
        )
        v1 = legacy_to_v1(legacy)
        self.assertIn("low_confidence", v1.risk_flags)

    def test_legacy_conflict_maps_to_risk_flag(self) -> None:
        legacy = AiSuggestion(
            question_id="C5-1",
            selected_codes=["C5-12"],
            confidence=0.8,
            evidence="no fuma",
            status="conflict",
        )
        v1 = legacy_to_v1(legacy)
        self.assertIn("conflict", v1.risk_flags)

    def test_free_text_adds_risk_flag(self) -> None:
        legacy = AiSuggestion(
            question_id="A1-1",
            selected_codes=[],
            free_text="trabajo en construccion",
            confidence=0.7,
            evidence="trabajo en construccion",
        )
        v1 = legacy_to_v1(legacy)
        self.assertIn("free_text", v1.risk_flags)

    def test_validated_inherits_labels(self) -> None:
        validated = ValidatedSuggestion(
            question_id="C5-1",
            selected_codes=["C5-12"],
            confidence=0.9,
            evidence="no fuma",
            question_text="Fuma?",
            question_type="yesno",
            module="history",
            section="HABITOS",
            selected_labels=["No"],
        )
        v1 = legacy_to_v1(validated)
        self.assertEqual(v1.selected_labels, ["No"])
        self.assertEqual(v1.module, "history")
        self.assertEqual(v1.section, "HABITOS")
        self.assertEqual(v1.question_text, "Fuma?")
        self.assertEqual(v1.question_type, "yesno")

    def test_audio_timestamps_propagated(self) -> None:
        legacy = AiSuggestion(
            question_id="C5-1",
            selected_codes=["C5-12"],
            confidence=0.9,
            evidence="no fuma",
        )
        v1 = legacy_to_v1(legacy, audio_start=12.3, audio_end=14.7)
        self.assertEqual(v1.audio_start, 12.3)
        self.assertEqual(v1.audio_end, 14.7)

    def test_speaker_normalization(self) -> None:
        cases = [
            ("medico", "medico"),
            ("SPEAKER_00", "unknown"),
            ("paciente", "paciente"),
            ("SPEAKER_01", "unknown"),
            ("acompanante", "acompanante"),
            (None, None),
            ("random", "unknown"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                legacy = AiSuggestion(
                    question_id="X",
                    selected_codes=[],
                    confidence=0.5,
                    evidence="x",
                    speaker=raw,
                )
                v1 = legacy_to_v1(legacy)
                self.assertEqual(v1.speaker, expected)

    def test_roundtrip_legacy_v1_legacy_preserves_core(self) -> None:
        legacy = AiSuggestion(
            question_id="C5-1",
            selected_codes=["C5-12"],
            free_text=None,
            confidence=0.82,
            evidence="no fuma",
            speaker="paciente",
            status="low_confidence",
        )
        v1 = legacy_to_v1(legacy)
        back = v1_to_legacy(v1)

        self.assertEqual(back.question_id, legacy.question_id)
        self.assertEqual(back.selected_codes, legacy.selected_codes)
        self.assertEqual(back.free_text, legacy.free_text)
        self.assertAlmostEqual(back.confidence, legacy.confidence)
        self.assertEqual(back.evidence, legacy.evidence)
        self.assertEqual(back.status, "low_confidence")


class QualityReportBuilderTest(unittest.TestCase):
    def test_aggregates_basic_counts(self) -> None:
        suggestions = [
            SuggestionV1(question_id="A", confidence=0.9, evidence="x"),
            SuggestionV1(
                question_id="B",
                confidence=0.4,
                evidence="y",
                risk_flags=["low_confidence"],
            ),
            SuggestionV1(
                question_id="C",
                confidence=0.0,
                evidence="",
                technical_status="discarded_by_graph",
                reason="not reachable",
            ),
        ]
        report = build_quality_report(
            questions_considered=10,
            suggestions=suggestions,
            provider="ollama",
            model="qwen2.5:7b-instruct",
            profile="prototype_local",
            extra={"schema_parse_fail_count": 1, "empty_generation_count": 0},
        )
        self.assertEqual(report.total_questions_considered, 10)
        self.assertEqual(report.suggestions_valid, 2)  # A y B son valid technical
        self.assertEqual(report.suggestions_needing_review, 1)  # B con low_confidence
        self.assertEqual(report.discarded_by_graph, 1)
        self.assertEqual(report.schema_parse_fail_count, 1)
        self.assertEqual(report.provider, "ollama")
        self.assertEqual(report.profile, "prototype_local")


if __name__ == "__main__":
    unittest.main()
