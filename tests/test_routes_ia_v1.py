"""Tests del endpoint v1 `POST /api/v1/ia/extract-from-text`.

Mockean Ollama y Cloudflare para no requerir servicios externos.
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
from app.main import app  # noqa: E402
from app.models.extraction_contract import SCHEMA_VERSION  # noqa: E402
from app.models.suggestion import AiSuggestion  # noqa: E402


class _FakeOllama:
    def __init__(self, suggestions: list[AiSuggestion] | None = None) -> None:
        self._suggestions = suggestions or []
        self.calls: list[dict[str, Any]] = []

    def extract(self, *, text: str, module: str, section: str, questions: list) -> list[AiSuggestion]:
        self.calls.append(
            {
                "text": text,
                "module": module,
                "section": section,
                "n_q": len(questions),
                "model": getattr(self, "model", None),
            }
        )
        return list(self._suggestions)


class _FakeCloudflare:
    def __init__(self, suggestions: list[AiSuggestion] | None = None) -> None:
        self._suggestions = suggestions or []
        self.calls: list[dict[str, Any]] = []

    def extract(self, *, text: str, module: str, section: str, questions: list) -> list[AiSuggestion]:
        self.calls.append(
            {"text": text, "module": module, "section": section, "n_q": len(questions)}
        )
        return list(self._suggestions)


class _FakeBatchingOllama:
    """Fake con firma posicional (como los providers reales) para el path batch."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def extract(self, text, module, section, questions, clinical_context=None):
        self.calls.append({"n_q": len(questions)})
        return []


# Texto que toca >20 temas del modulo history -> narrow deja muchas preguntas.
_RICH_HISTORY_TEXT = (
    "He trabajado diez anos en el sector tecnologico expuesto a pantallas. "
    "Trabajo ocho horas, riesgos ergonomicos de postura. No uso equipos de "
    "proteccion individual. Mi padre tiene hipertension y colesterol. Mi madre "
    "ninguna enfermedad. Tuve gastritis del aparato digestivo. No tomo "
    "medicacion. Me operaron de una hernia inguinal. No fumo pero deje de fumar "
    "hace anos. Consumo alcohol ocasionalmente. No tengo alergias. Camino y voy "
    "al gimnasio varias veces por semana."
)


class RoutesIaV1Test(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        # Limpiar caches lru
        deps.get_ollama_provider.cache_clear()
        deps.get_cloudflare_provider.cache_clear()

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    # ---------- happy paths ----------

    def test_heuristic_only_path_returns_v1_shape(self) -> None:
        # Forzar heuristic via ia_provider override
        body = {
            "module": "history",
            "section": "HABITOS",
            "text": "El paciente no fuma actualmente y nunca ha fumado.",
            "ia_provider": "heuristic",
        }
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["schema_version"], SCHEMA_VERSION)
        self.assertEqual(data["module"], "history")
        self.assertEqual(data["section"], "HABITOS")
        self.assertIn("suggestions", data)
        self.assertIn("graph_report", data)
        self.assertIn("quality_report", data)
        self.assertIsNone(data["transcription"])

        # graph_report con entry del modulo
        self.assertIsNotNone(data["graph_report"]["entry_question_id"])

        # quality_report con provider correcto
        self.assertEqual(data["quality_report"]["provider"], "heuristic")
        self.assertGreater(data["quality_report"]["total_questions_considered"], 0)

    def test_ollama_provider_override(self) -> None:
        fake = _FakeOllama(
            suggestions=[
                AiSuggestion(
                    question_id="C5-1",
                    selected_codes=["C5-12"],
                    confidence=0.9,
                    evidence="no fuma",
                ),
            ]
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

        self.assertEqual(len(data["suggestions"]), 1)
        sugg = data["suggestions"][0]
        self.assertEqual(sugg["question_id"], "C5-1")
        self.assertEqual(sugg["selected_codes"], ["C5-12"])
        self.assertEqual(sugg["technical_status"], "valid")
        self.assertEqual(sugg["review_status"], "pending")
        self.assertNotIn("online_provider_used", sugg["risk_flags"])
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(data["quality_report"]["provider"], "ollama")

    def test_ollama_model_override_uses_requested_local_model(self) -> None:
        fake = _FakeOllama(
            suggestions=[
                AiSuggestion(
                    question_id="C5-1",
                    selected_codes=["C5-12"],
                    confidence=0.9,
                    evidence="no fuma",
                ),
            ]
        )
        app.dependency_overrides[deps.get_ollama_provider] = lambda: fake

        body = {
            "module": "history",
            "section": "HABITOS",
            "text": "no fuma",
            "ia_provider": "ollama",
            "ia_model": "qwen3:8b",
        }
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()

        self.assertEqual(fake.calls[0]["model"], "qwen3:8b")
        self.assertEqual(data["quality_report"]["model"], "qwen3:8b")

    def test_unknown_ollama_model_returns_400(self) -> None:
        body = {
            "module": "history",
            "section": "HABITOS",
            "text": "no fuma",
            "ia_provider": "ollama",
            "ia_model": "modelo-no-permitido:1b",
        }
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        self.assertEqual(r.status_code, 400)

    def test_providers_include_qwen3_ollama_option(self) -> None:
        r = self.client.get("/api/ia/providers")
        self.assertEqual(r.status_code, 200, r.text)
        ollama = next(item for item in r.json()["providers"] if item["name"] == "ollama")
        self.assertIn("qwen3:8b", ollama["models"])

    def test_cloudflare_provider_adds_online_risk_flag(self) -> None:
        fake = _FakeCloudflare(
            suggestions=[
                AiSuggestion(
                    question_id="C5-1",
                    selected_codes=["C5-12"],
                    confidence=0.92,
                    evidence="no fuma",
                ),
            ]
        )
        app.dependency_overrides[deps.get_cloudflare_provider] = lambda: fake

        body = {
            "module": "history",
            "section": "HABITOS",
            "text": "no fuma",
            "ia_provider": "cloudflare",
        }
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        sugg = data["suggestions"][0]
        self.assertIn("online_provider_used", sugg["risk_flags"])
        self.assertEqual(data["quality_report"]["provider"], "cloudflare")

    def test_module_wide_does_not_discard_by_graph(self) -> None:
        # Sugerencia valida y anclada para C8-1 (actividad fisica). El entry A1-1
        # no se captura, asi que el grafo la marca "no alcanzable". En module-wide
        # NO debe degradarse a discarded_by_graph: la entrevista libre no es un
        # recorrido secuencial.
        sugg = AiSuggestion(
            question_id="C8-1",
            selected_codes=["C8-11"],
            confidence=0.9,
            evidence="camino varias veces por semana y voy al gimnasio",
        )

        class _FakeBatchOne:
            def extract(self, text, module, section, questions, clinical_context=None):
                ids = {q["id"] for q in questions}
                return [sugg] if "C8-1" in ids else []

        app.dependency_overrides[deps.get_ollama_provider] = lambda: _FakeBatchOne()
        body = {
            "module": "history",
            "section": "*",
            "text": _RICH_HISTORY_TEXT,
            "ia_provider": "ollama",
        }
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        c8 = next((s for s in data["suggestions"] if s["question_id"] == "C8-1"), None)
        self.assertIsNotNone(c8, "C8-1 debe sobrevivir en module-wide")
        self.assertEqual(c8["technical_status"], "valid")
        self.assertEqual(data["quality_report"]["discarded_by_graph"], 0)

    def test_module_wide_auto_batches_extraction(self) -> None:
        # section "*" = modulo completo (106 preguntas). El narrow deja muchas;
        # debe trocear en lotes para no enviar todo en una llamada (timeout/trunc).
        fake = _FakeBatchingOllama()
        app.dependency_overrides[deps.get_ollama_provider] = lambda: fake
        body = {
            "module": "history",
            "section": "*",
            "text": _RICH_HISTORY_TEXT,
            "ia_provider": "ollama",
        }
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        # Mas de una llamada (batched) y ninguna excede batch_size (default 6).
        self.assertGreater(len(fake.calls), 1, "module-wide debe trocear en lotes")
        self.assertLessEqual(max(c["n_q"] for c in fake.calls), 6)

    # ---------- error paths ----------

    def test_invalid_module_returns_422(self) -> None:
        body = {"module": "wrong", "section": "X", "text": "y"}
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        self.assertEqual(r.status_code, 422)

    def test_unknown_section_returns_404(self) -> None:
        body = {
            "module": "history",
            "section": "ESTA_SECCION_NO_EXISTE",
            "text": "x",
        }
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        self.assertEqual(r.status_code, 404)

    def test_empty_text_returns_422(self) -> None:
        body = {"module": "history", "section": "HABITOS", "text": ""}
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        self.assertEqual(r.status_code, 422)

    def test_cloudflare_unconfigured_returns_500(self) -> None:
        app.dependency_overrides[deps.get_cloudflare_provider] = lambda: None
        body = {
            "module": "history",
            "section": "HABITOS",
            "text": "no fuma",
            "ia_provider": "cloudflare",
        }
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        self.assertEqual(r.status_code, 500)
        self.assertIn("Cloudflare", r.json()["detail"])

    def test_invalid_provider_falls_back_to_default(self) -> None:
        # provider "fantasma" → cae al default del entorno (ia_provider de settings)
        body = {
            "module": "history",
            "section": "HABITOS",
            "text": "no fuma",
            "ia_provider": "model_X_no_existe",
        }
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        # No falla 422 porque ia_provider es str libre; cae al default.
        self.assertEqual(r.status_code, 200, r.text)

    # ---------- shape ----------

    def test_response_contract_strict_no_extra_fields(self) -> None:
        body = {
            "module": "history",
            "section": "HABITOS",
            "text": "no fuma",
            "ia_provider": "heuristic",
        }
        r = self.client.post("/api/v1/ia/extract-from-text", json=body)
        data = r.json()
        # campos top-level esperados
        expected = {
            "schema_version",
            "module",
            "section",
            "suggestions",
            "graph_report",
            "quality_report",
            "transcription",
            "clinical_summary",
        }
        self.assertEqual(set(data.keys()), expected)


if __name__ == "__main__":
    unittest.main()
