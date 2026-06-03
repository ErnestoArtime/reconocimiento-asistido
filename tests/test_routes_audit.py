"""Tests del endpoint /api/v1/audit/* (Hito 11.5)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.api import routes_audit  # noqa: E402
from app.core import config  # noqa: E402
from app.main import app  # noqa: E402


class AuditEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.audit_path = Path(self.tmp.name) / "audit.log.jsonl"
        # Forzar config a usar tmp + secret de test
        os.environ["AUDIT_LOG_PATH"] = str(self.audit_path)
        os.environ["AUDIT_HMAC_KEY"] = "test-secret"
        routes_audit._get_audit_log.cache_clear()

        self.client = TestClient(app)

    def tearDown(self) -> None:
        os.environ.pop("AUDIT_LOG_PATH", None)
        os.environ.pop("AUDIT_HMAC_KEY", None)
        routes_audit._get_audit_log.cache_clear()
        config.get_settings.cache_clear()
        app.dependency_overrides.clear()
        self.tmp.cleanup()

    def test_append_and_verify_roundtrip(self) -> None:
        # demo profile = no auth obligatoria
        body = {
            "action": "suggestion_accepted",
            "user_id": "doctor1",
            "patient_id": "p_001",
            "question_id": "C5-1",
            "selected_codes": ["C5-12"],
            "evidence": "el paciente no fuma actualmente",
            "confidence": 0.92,
        }
        r = self.client.post("/api/v1/audit/events", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["chain_hmac"]), 64)
        self.assertEqual(data["prev_chain_hmac"], "0" * 64)

        # Verify
        r2 = self.client.get("/api/v1/audit/verify")
        self.assertEqual(r2.status_code, 200, r2.text)
        v = r2.json()
        self.assertTrue(v["ok"])
        self.assertEqual(v["n_entries"], 1)
        self.assertIsNone(v["error"])

    def test_evidence_not_persisted_in_clear(self) -> None:
        evidence = "PII_SENSIBLE_QUE_NO_DEBE_APARECER_EN_DISCO"
        self.client.post(
            "/api/v1/audit/events",
            json={
                "action": "suggestion_accepted",
                "user_id": "d1",
                "patient_id": "p_001",
                "question_id": "C5-1",
                "selected_codes": ["C5-12"],
                "evidence": evidence,
                "confidence": 0.9,
            },
        )
        content = self.audit_path.read_text(encoding="utf-8")
        self.assertNotIn(evidence, content)

    def test_list_events_returns_entries(self) -> None:
        for i in range(3):
            self.client.post(
                "/api/v1/audit/events",
                json={
                    "action": "suggestion_accepted",
                    "user_id": f"d{i}",
                    "patient_id": f"p_{i:03d}",
                    "question_id": "C5-1",
                    "selected_codes": ["C5-12"],
                    "evidence": f"ev {i}",
                    "confidence": 0.8,
                },
            )
        r = self.client.get("/api/v1/audit/events?n=10")
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["total"], 3)
        self.assertEqual(len(data["entries"]), 3)
        # Cada entry tiene chain_hmac
        for e in data["entries"]:
            self.assertEqual(len(e["chain_hmac"]), 64)

    def test_list_events_n_clamped(self) -> None:
        r = self.client.get("/api/v1/audit/events?n=0")
        self.assertEqual(r.status_code, 400)
        r = self.client.get("/api/v1/audit/events?n=99999")
        self.assertEqual(r.status_code, 400)

    def test_invalid_action_returns_422(self) -> None:
        r = self.client.post(
            "/api/v1/audit/events",
            json={
                "action": "INVALID_ACTION",
                "user_id": "d1",
                "patient_id": "p_001",
            },
        )
        self.assertEqual(r.status_code, 422)

    def test_503_when_audit_not_configured(self) -> None:
        # Quitar secret
        os.environ.pop("AUDIT_HMAC_KEY", None)
        routes_audit._get_audit_log.cache_clear()

        r = self.client.get("/api/v1/audit/verify")
        self.assertEqual(r.status_code, 503)
        self.assertIn("Audit log no configurado", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
