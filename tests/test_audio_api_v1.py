from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from app.models.extraction_contract import SCHEMA_VERSION  # noqa: E402
from app.services.audio.base import Segment, TranscriptResult  # noqa: E402


class AudioApiV1Test(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_v1_transcribe_and_extract_returns_contract_with_timestamps(self) -> None:
        transcript = TranscriptResult(
            text=(
                "Cuero cabelludo normal. Cara normal. Boca normal. "
                "Oidos normales. Ojos normales. Nariz normal."
            ),
            language="es",
            duration_s=6.0,
            rtf=0.2,
            provider="fake_stt",
            model="fake-model",
            segments=[
                Segment(start=0.0, end=1.0, text="Cuero cabelludo normal."),
                Segment(start=1.0, end=2.0, text="Cara normal."),
                Segment(start=2.0, end=3.0, text="Boca normal."),
                Segment(start=3.0, end=4.0, text="Oidos normales."),
                Segment(start=4.0, end=5.0, text="Ojos normales."),
                Segment(start=5.0, end=6.0, text="Nariz normal."),
            ],
        )

        with patch("app.api.routes_audio.transcribe_upload", return_value=transcript):
            response = self.client.post(
                "/api/v1/audio/transcribe-and-extract",
                data={
                    "module": "exam",
                    "section": "CABEZA",
                    "ia_provider": "heuristic",
                    "use_clinical_prompt": "false",
                    "use_cache": "false",
                },
                files={"audio": ("sample.wav", b"fake audio", "audio/wav")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
        self.assertEqual(payload["module"], "exam")
        self.assertEqual(payload["section"], "CABEZA")
        self.assertEqual(payload["transcription"]["provider"], "fake_stt")
        self.assertEqual(
            payload["graph_report"]["path"],
            ["E1-1", "E1-2", "E1-3", "E1-4", "E1-5", "E1-6"],
        )
        self.assertGreaterEqual(len(payload["suggestions"]), 6)
        self.assertTrue(
            all(item["audio_start"] is not None for item in payload["suggestions"])
        )
        self.assertEqual(payload["quality_report"]["provider"], "heuristic")
        self.assertEqual(payload["quality_report"]["evidence_without_timestamp"], 0)

    def test_v1_transcribe_and_extract_flags_missing_timestamp(self) -> None:
        transcript = TranscriptResult(
            text="La boca esta normal.",
            language="es",
            duration_s=2.0,
            rtf=0.2,
            provider="fake_stt",
            model="fake-model",
            segments=[Segment(start=0.0, end=1.0, text="Otro segmento.")],
        )

        with patch("app.api.routes_audio.transcribe_upload", return_value=transcript):
            response = self.client.post(
                "/api/v1/audio/transcribe-and-extract",
                data={
                    "module": "exam",
                    "section": "CABEZA",
                    "ia_provider": "heuristic",
                    "use_clinical_prompt": "false",
                    "use_cache": "false",
                },
                files={"audio": ("sample.wav", b"fake audio", "audio/wav")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["suggestions"])
        self.assertIn("no_audio_timestamp", payload["suggestions"][0]["risk_flags"])
        self.assertGreaterEqual(payload["quality_report"]["evidence_without_timestamp"], 1)

    def test_v1_audio_marks_unexpected_speaker_for_history(self) -> None:
        transcript = TranscriptResult(
            text="No fuma actualmente.",
            language="es",
            duration_s=2.0,
            rtf=0.2,
            provider="fake_stt",
            model="fake-model",
            segments=[
                Segment(
                    start=0.0,
                    end=2.0,
                    text="No fuma actualmente.",
                    speaker="medico",
                )
            ],
        )

        with patch("app.api.routes_audio.transcribe_upload", return_value=transcript):
            response = self.client.post(
                "/api/v1/audio/transcribe-and-extract",
                data={
                    "module": "history",
                    "section": "HABITOS",
                    "ia_provider": "heuristic",
                    "use_clinical_prompt": "false",
                    "use_cache": "false",
                },
                files={"audio": ("sample.wav", b"fake audio", "audio/wav")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["suggestions"])
        first = payload["suggestions"][0]
        self.assertEqual(first["speaker"], "medico")
        self.assertIn("speaker_not_expected", first["risk_flags"])


if __name__ == "__main__":
    unittest.main()
