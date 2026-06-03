"""Tests del resumen clinico intermedio.

Cubre el servicio (unitario) y el wiring en el endpoint v1 con el flag activo.
No requiere servicios externos: los providers se mockean.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.api import deps  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.models.suggestion import AiSuggestion  # noqa: E402
from app.services.clinical_summary_service import generate_clinical_summary  # noqa: E402


class _FakeSummarizer:
    def __init__(self, summary: str = "", *, raises: bool = False) -> None:
        self._summary = summary
        self._raises = raises
        self.calls: list[str] = []

    def summarize(self, text: str) -> str:
        self.calls.append(text)
        if self._raises:
            raise RuntimeError("boom")
        return self._summary


class GenerateClinicalSummaryTest(unittest.TestCase):
    def test_returns_trimmed_summary(self) -> None:
        fake = _FakeSummarizer("  Habitos: no fuma.  ")
        self.assertEqual(generate_clinical_summary("texto", fake), "Habitos: no fuma.")
        self.assertEqual(fake.calls, ["texto"])

    def test_empty_text_skips_summarizer(self) -> None:
        fake = _FakeSummarizer("algo")
        self.assertEqual(generate_clinical_summary("   ", fake), "")
        self.assertEqual(fake.calls, [])

    def test_provider_failure_returns_empty(self) -> None:
        fake = _FakeSummarizer(raises=True)
        self.assertEqual(generate_clinical_summary("texto", fake), "")


class _FakeOllamaWithSummary:
    def __init__(self, summary: str, suggestions: list[AiSuggestion]) -> None:
        self._summary = summary
        self._suggestions = suggestions
        self.extract_calls: list[dict[str, Any]] = []
        self.summarize_calls: list[str] = []

    def summarize(self, text: str) -> str:
        self.summarize_calls.append(text)
        return self._summary

    def extract(
        self,
        *,
        text: str,
        module: str,
        section: str,
        questions: list,
        clinical_context: str | None = None,
    ) -> list[AiSuggestion]:
        self.extract_calls.append(
            {"text": text, "clinical_context": clinical_context, "n_q": len(questions)}
        )
        return list(self._suggestions)


class ClinicalSummaryV1WiringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        deps.get_ollama_provider.cache_clear()
        deps.get_cloudflare_provider.cache_clear()

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_summary_in_response_and_passed_as_context(self) -> None:
        fake = _FakeOllamaWithSummary(
            summary="Habitos: no fuma.",
            suggestions=[
                AiSuggestion(
                    question_id="C5-1",
                    selected_codes=["C5-12"],
                    confidence=0.9,
                    evidence="no fuma",
                )
            ],
        )
        app.dependency_overrides[deps.get_ollama_provider] = lambda: fake
        body = {
            "module": "history",
            "section": "HABITOS",
            "text": "no fuma",
            "ia_provider": "ollama",
        }
        with patch.object(get_settings(), "ia_clinical_summary_enabled", True):
            r = self.client.post("/api/v1/ia/extract-from-text", json=body)

        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["clinical_summary"], "Habitos: no fuma.")
        self.assertEqual(fake.summarize_calls, ["no fuma"])
        self.assertEqual(fake.extract_calls[0]["clinical_context"], "Habitos: no fuma.")

    def test_summary_null_when_flag_off(self) -> None:
        fake = _FakeOllamaWithSummary(
            summary="no deberia llamarse",
            suggestions=[
                AiSuggestion(
                    question_id="C5-1",
                    selected_codes=["C5-12"],
                    confidence=0.9,
                    evidence="no fuma",
                )
            ],
        )
        app.dependency_overrides[deps.get_ollama_provider] = lambda: fake
        body = {
            "module": "history",
            "section": "HABITOS",
            "text": "no fuma",
            "ia_provider": "ollama",
        }
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertIsNone(data["clinical_summary"])
        self.assertEqual(fake.summarize_calls, [])
        self.assertIsNone(fake.extract_calls[0]["clinical_context"])


if __name__ == "__main__":
    unittest.main()
