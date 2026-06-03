from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402


# Texto de entrevista libre: el medico salta entre secciones (boca, oido, ojos)
# sin ceñirse a una. Antes habia que fijar una seccion en el combo.
FREE_INTERVIEW = (
    "Cuero cabelludo normal. La cara esta normal. La boca esta normal. "
    "El oido derecho presenta un tapon de cerumen. Ojos normales. Nariz normal."
)


class ModuleWideExtractionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_v1_without_section_extracts_over_whole_module(self) -> None:
        response = self.client.post(
            "/api/v1/ia/extract-from-text",
            json={
                "module": "exam",
                "text": FREE_INTERVIEW,
                "ia_provider": "heuristic",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["module"], "exam")
        self.assertEqual(payload["section"], "*")
        self.assertIsInstance(payload["suggestions"], list)
        self.assertTrue(payload["suggestions"], "esperaba sugerencias del modulo completo")

    def test_v1_section_star_is_module_wide(self) -> None:
        response = self.client.post(
            "/api/v1/ia/extract-from-text",
            json={
                "module": "exam",
                "section": "*",
                "text": FREE_INTERVIEW,
                "ia_provider": "heuristic",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["section"], "*")

    def test_v1_concrete_section_still_filters(self) -> None:
        response = self.client.post(
            "/api/v1/ia/extract-from-text",
            json={
                "module": "exam",
                "section": "CABEZA",
                "text": FREE_INTERVIEW,
                "ia_provider": "heuristic",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["section"], "CABEZA")

    def test_legacy_endpoint_without_section_is_module_wide(self) -> None:
        response = self.client.post(
            "/api/ia/extract-from-text",
            json={
                "module": "exam",
                "text": FREE_INTERVIEW,
                "ia_provider": "heuristic",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["section"], "*")


if __name__ == "__main__":
    unittest.main()
