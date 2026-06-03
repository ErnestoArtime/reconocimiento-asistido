"""Tests del flag `use_json_schema` en OllamaProvider (Hito 2.2)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.llm_provider import OllamaProvider  # noqa: E402


def _q(qid: str, codes: dict | None = None, qtype: str = "yesno") -> dict:
    return {
        "id": qid,
        "text": f"Pregunta {qid}",
        "question_type": qtype,
        "codes": codes or {f"{qid}-1": "Si", f"{qid}-2": "No"},
        "section": "TEST",
    }


class ResolveFormatTest(unittest.TestCase):
    def test_default_returns_json_string(self) -> None:
        provider = OllamaProvider(base_url="http://x", model="m")
        self.assertFalse(provider.use_json_schema)
        result = provider._resolve_format([_q("Q1")])
        self.assertEqual(result, "json")

    def test_schema_enabled_returns_dict(self) -> None:
        provider = OllamaProvider(
            base_url="http://x",
            model="m",
            use_json_schema=True,
        )
        result = provider._resolve_format([_q("Q1")])
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("type"), "object")
        self.assertIn("suggestions", result.get("properties", {}))

    def test_schema_enabled_but_too_many_questions_falls_back(self) -> None:
        provider = OllamaProvider(
            base_url="http://x",
            model="m",
            use_json_schema=True,
            schema_max_questions=5,
        )
        questions = [_q(f"Q{i}") for i in range(10)]
        result = provider._resolve_format(questions)
        self.assertEqual(result, "json", "10 questions > limit 5 → fallback json")

    def test_schema_enabled_with_empty_questions_falls_back(self) -> None:
        provider = OllamaProvider(
            base_url="http://x",
            model="m",
            use_json_schema=True,
        )
        self.assertEqual(provider._resolve_format([]), "json")

    def test_schema_restricts_codes_per_question(self) -> None:
        provider = OllamaProvider(
            base_url="http://x",
            model="m",
            use_json_schema=True,
        )
        q = _q("E1-3", codes={"E1-31": "Si", "E1-32": "No"})
        schema = provider._resolve_format([q])
        variants = schema["properties"]["suggestions"]["items"]["anyOf"]
        self.assertEqual(len(variants), 1)
        variant = variants[0]
        self.assertEqual(variant["properties"]["question_id"]["const"], "E1-3")
        allowed_codes = variant["properties"]["selected_codes"]["items"]["enum"]
        self.assertEqual(sorted(allowed_codes), ["E1-31", "E1-32"])


def _mock_client_capturing(content_by_call: list[str]) -> tuple[Any, list]:
    """Devuelve (MockClient, formats) donde formats acumula el `format` enviado.

    `content_by_call` da el `message.content` por llamada (la i-esima post usa
    el i-esimo contenido; la ultima se repite si hay mas llamadas).
    """
    formats: list = []
    state = {"i": 0}

    def _post(url, json):
        formats.append(json.get("format"))
        idx = min(state["i"], len(content_by_call) - 1)
        state["i"] += 1
        response = MagicMock()
        response.json.return_value = {"message": {"content": content_by_call[idx]}}
        response.raise_for_status.return_value = None
        return response

    MockClient = MagicMock()
    client_instance = MagicMock()
    client_instance.post = MagicMock(side_effect=_post)
    MockClient.return_value.__enter__.return_value = client_instance
    return MockClient, formats


class PayloadIntegrationTest(unittest.TestCase):
    def test_payload_uses_string_json_by_default(self) -> None:
        provider = OllamaProvider(base_url="http://x", model="m")
        MockClient, formats = _mock_client_capturing(["{}"])
        with patch("app.services.llm_provider.httpx.Client", MockClient):
            provider.extract(text="x", module="exam", section="TEST", questions=[_q("Q")])
        self.assertEqual(formats, ["json"])

    def test_payload_uses_schema_when_flag_on(self) -> None:
        provider = OllamaProvider(base_url="http://x", model="m", use_json_schema=True)
        # Primera respuesta trae payload valido -> sin reintento.
        MockClient, formats = _mock_client_capturing(['{"suggestions": []}'])
        with patch("app.services.llm_provider.httpx.Client", MockClient):
            provider.extract(text="x", module="exam", section="TEST", questions=[_q("Q")])
        self.assertEqual(len(formats), 1)
        self.assertIsInstance(formats[0], dict)
        self.assertEqual(formats[0]["type"], "object")


class ThinkFlagTest(unittest.TestCase):
    def test_think_false_sent_in_payload(self) -> None:
        provider = OllamaProvider(base_url="http://x", model="m", think=False)
        captured = {}
        with patch("app.services.llm_provider.httpx.Client") as MockClient:
            client_instance = MagicMock()
            response = MagicMock()
            response.json.return_value = {"message": {"content": '{"suggestions": []}'}}
            response.raise_for_status.return_value = None
            client_instance.post = MagicMock(
                side_effect=lambda url, json: (captured.update(json) or response)
            )
            MockClient.return_value.__enter__.return_value = client_instance
            provider.extract(text="x", module="exam", section="TEST", questions=[_q("Q")])
        self.assertIn("think", captured)
        self.assertFalse(captured["think"])

    def test_think_none_omits_field(self) -> None:
        provider = OllamaProvider(base_url="http://x", model="m")  # think default None
        captured = {}
        with patch("app.services.llm_provider.httpx.Client") as MockClient:
            client_instance = MagicMock()
            response = MagicMock()
            response.json.return_value = {"message": {"content": '{"suggestions": []}'}}
            response.raise_for_status.return_value = None
            client_instance.post = MagicMock(
                side_effect=lambda url, json: (captured.update(json) or response)
            )
            MockClient.return_value.__enter__.return_value = client_instance
            provider.extract(text="x", module="exam", section="TEST", questions=[_q("Q")])
        self.assertNotIn("think", captured)


class SchemaFallbackTest(unittest.TestCase):
    def test_empty_generation_retries_with_plain_json(self) -> None:
        provider = OllamaProvider(base_url="http://x", model="m", use_json_schema=True)
        # 1) schema -> vacio (sin payload). 2) json plano -> sugerencia valida.
        good = '{"suggestions": [{"question_id": "Q", "selected_codes": ["Q-1"], "confidence": 0.8, "evidence": "si"}]}'
        MockClient, formats = _mock_client_capturing(["", good])
        with patch("app.services.llm_provider.httpx.Client", MockClient):
            out = provider.extract(
                text="x", module="exam", section="TEST", questions=[_q("Q")]
            )
        self.assertIsInstance(formats[0], dict)   # primer intento: schema
        self.assertEqual(formats[1], "json")       # reintento: json plano
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].question_id, "Q")

    def test_broken_json_retries_with_plain_json(self) -> None:
        provider = OllamaProvider(base_url="http://x", model="m", use_json_schema=True)
        MockClient, formats = _mock_client_capturing(["no json aqui", '{"suggestions": []}'])
        with patch("app.services.llm_provider.httpx.Client", MockClient):
            provider.extract(text="x", module="exam", section="TEST", questions=[_q("Q")])
        self.assertEqual(len(formats), 2)
        self.assertEqual(formats[1], "json")

    def test_valid_empty_payload_does_not_retry(self) -> None:
        provider = OllamaProvider(base_url="http://x", model="m", use_json_schema=True)
        MockClient, formats = _mock_client_capturing(['{"suggestions": []}'])
        with patch("app.services.llm_provider.httpx.Client", MockClient):
            provider.extract(text="x", module="exam", section="TEST", questions=[_q("Q")])
        self.assertEqual(len(formats), 1, "payload valido vacio no debe reintentar")

    def test_schema_off_never_retries(self) -> None:
        provider = OllamaProvider(base_url="http://x", model="m", use_json_schema=False)
        MockClient, formats = _mock_client_capturing([""])
        with patch("app.services.llm_provider.httpx.Client", MockClient):
            provider.extract(text="x", module="exam", section="TEST", questions=[_q("Q")])
        self.assertEqual(formats, ["json"])


if __name__ == "__main__":
    unittest.main()
