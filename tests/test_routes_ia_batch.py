"""Tests del flag IA_BATCH_EXTRACTION_THRESHOLD (Hito 6.1)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.api import deps  # noqa: E402
from app.core import config  # noqa: E402
from app.main import app  # noqa: E402
from app.models.suggestion import AiSuggestion  # noqa: E402


class _CountingOllama:
    """Mock que cuenta cuantas veces `extract` se llama (1 = monolitico, N = batches)."""

    def __init__(self) -> None:
        self.calls: list[int] = []

    def extract(self, text, module, section, questions):
        self.calls.append(len(questions))
        return [
            AiSuggestion(
                question_id=q["id"],
                selected_codes=[next(iter(q["codes"].keys()))],
                confidence=0.9,
                evidence="x",
            )
            for q in questions
        ]


class BatchExtractionFlagTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        deps.get_ollama_provider.cache_clear()
        deps.get_cloudflare_provider.cache_clear()

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        # Reset settings if mutated
        config.get_settings.cache_clear()

    def _force_settings(self, threshold: int, size: int = 3) -> None:
        """Mutate settings in-place via lru_cache instance (test only)."""
        s = config.get_settings()
        s.ia_batch_extraction_threshold = threshold
        s.ia_batch_extraction_size = size

    def test_threshold_zero_calls_extractor_once(self) -> None:
        """Default: threshold=0 → extractor monolitico, una sola llamada."""
        fake = _CountingOllama()
        app.dependency_overrides[deps.get_ollama_provider] = lambda: fake
        self._force_settings(threshold=0)

        body = {
            "module": "history",
            "section": "HABITOS",
            "text": "El paciente no fuma actualmente.",
            "ia_provider": "ollama",
        }
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(fake.calls), 1, "Sin batch, 1 llamada")

    def test_threshold_low_triggers_batching(self) -> None:
        """threshold=2 con seccion de 9 preguntas + batch_size=3 → 3 llamadas."""
        fake = _CountingOllama()
        app.dependency_overrides[deps.get_ollama_provider] = lambda: fake
        self._force_settings(threshold=2, size=3)

        body = {
            "module": "history",
            "section": "HABITOS",
            "text": "El paciente no fuma actualmente.",
            "ia_provider": "ollama",
        }
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertGreater(len(fake.calls), 1, "Con batch debe haber >1 llamadas")
        # Cada batch debe respetar size
        for n in fake.calls:
            self.assertLessEqual(n, 3)

    def test_threshold_above_question_count_no_batching(self) -> None:
        """threshold=100 con seccion < 100 → no se activa batch."""
        fake = _CountingOllama()
        app.dependency_overrides[deps.get_ollama_provider] = lambda: fake
        self._force_settings(threshold=100, size=3)

        body = {
            "module": "history",
            "section": "HABITOS",
            "text": "x",
            "ia_provider": "ollama",
        }
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(fake.calls), 1)

    def test_heuristic_provider_not_batched_even_with_threshold(self) -> None:
        """heuristic es rapido y sincrono. Batch no aplica."""
        self._force_settings(threshold=2, size=3)

        body = {
            "module": "history",
            "section": "HABITOS",
            "text": "no fuma actualmente",
            "ia_provider": "heuristic",
        }
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        # Solo verifica que no peta (no podemos contar calls del heuristico)
        self.assertEqual(r.status_code, 200, r.text)


if __name__ == "__main__":
    unittest.main()
