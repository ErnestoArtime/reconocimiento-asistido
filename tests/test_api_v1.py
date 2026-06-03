from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from app.models.extraction_contract import SCHEMA_VERSION  # noqa: E402


class ExtractionApiV1Test(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_legacy_extract_endpoint_still_works(self) -> None:
        response = self.client.post(
            "/api/ia/extract-from-text",
            json={
                "module": "exam",
                "section": "CABEZA",
                "text": "La boca esta normal. El oido derecho presenta un tapon de cerumen.",
                "ia_provider": "heuristic",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["module"], "exam")
        self.assertEqual(payload["section"], "CABEZA")
        self.assertEqual(payload["ia_provider_used"], "heuristic")
        self.assertIn("suggestions", payload)
        self.assertNotIn("schema_version", payload)

    def test_v1_extract_endpoint_returns_versioned_contract(self) -> None:
        response = self.client.post(
            "/api/v1/ia/extract-from-text",
            json={
                "module": "exam",
                "section": "CABEZA",
                "text": (
                    "Cuero cabelludo normal. Cara normal. Boca normal. "
                    "Oidos normales. Ojos normales. Nariz normal."
                ),
                "ia_provider": "heuristic",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
        self.assertEqual(payload["module"], "exam")
        self.assertEqual(payload["section"], "CABEZA")
        self.assertIsInstance(payload["suggestions"], list)
        self.assertIsInstance(payload["graph_report"], dict)
        self.assertIsInstance(payload["quality_report"], dict)
        self.assertIsNone(payload["transcription"])
        self.assertEqual(
            payload["graph_report"]["path"],
            ["E1-1", "E1-2", "E1-3", "E1-4", "E1-5", "E1-6"],
        )
        self.assertEqual(payload["graph_report"]["missing_required"], [])
        self.assertEqual(payload["graph_report"]["discarded"], [])

        first = payload["suggestions"][0]
        self.assertIn("technical_status", first)
        self.assertIn("review_status", first)
        self.assertIn("risk_flags", first)
        self.assertEqual(first["review_status"], "pending")

        quality = payload["quality_report"]
        self.assertEqual(quality["provider"], "heuristic")
        self.assertEqual(
            quality["suggestions_valid"],
            len(payload["suggestions"]),
        )

    def test_v1_unknown_section_returns_404(self) -> None:
        response = self.client.post(
            "/api/v1/ia/extract-from-text",
            json={
                "module": "exam",
                "section": "NO_EXISTE",
                "text": "texto",
                "ia_provider": "heuristic",
            },
        )

        self.assertEqual(response.status_code, 404)

    def test_v1_quality_report_includes_graph_missing_required_count(self) -> None:
        response = self.client.post(
            "/api/v1/ia/extract-from-text",
            json={
                "module": "exam",
                "section": "CABEZA",
                "text": "La boca esta normal.",
                "ia_provider": "heuristic",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["graph_report"]["missing_required"], ["E1-1"])
        self.assertEqual(payload["quality_report"]["missing_required"], 1)


if __name__ == "__main__":
    unittest.main()
