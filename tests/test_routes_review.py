"""Tests del endpoint PATCH /api/v1/suggestions/{id}/review (Hito V3)."""
from __future__ import annotations

import json
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


class ReviewEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.audit_path = Path(self.tmp.name) / "audit.log.jsonl"
        os.environ["AUDIT_LOG_PATH"] = str(self.audit_path)
        os.environ["AUDIT_HMAC_KEY"] = "test-review-secret"
        routes_audit._get_audit_log.cache_clear()
        config.get_settings.cache_clear()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        os.environ.pop("AUDIT_LOG_PATH", None)
        os.environ.pop("AUDIT_HMAC_KEY", None)
        routes_audit._get_audit_log.cache_clear()
        config.get_settings.cache_clear()
        app.dependency_overrides.clear()
        self.tmp.cleanup()

    def _body(self, decision: str, **overrides) -> dict:
        body = {
            "decision": decision,
            "user_id": "doctor1",
            "patient_id": "p_001",
            "question_id": "C5-1",
            "selected_codes": ["C5-12"],
            "evidence": "el paciente no fuma",
            "confidence": 0.92,
        }
        body.update(overrides)
        return body

    def test_accepted_creates_audit_entry(self) -> None:
        r = self.client.patch(
            "/api/v1/suggestions/sugg_001/review",
            json=self._body("accepted"),
        )
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["decision"], "accepted")
        self.assertEqual(data["suggestion_id"], "sugg_001")
        self.assertEqual(len(data["chain_hmac"]), 64)

        # Verify audit file contains the entry
        content = self.audit_path.read_text(encoding="utf-8")
        record = json.loads(content.splitlines()[0])
        self.assertEqual(record["action"], "suggestion_accepted")
        self.assertEqual(record["extra"]["suggestion_id"], "sugg_001")

    def test_edited_creates_audit_entry(self) -> None:
        r = self.client.patch(
            "/api/v1/suggestions/sugg_002/review",
            json=self._body("edited", selected_codes=["C5-11"]),
        )
        self.assertEqual(r.status_code, 200, r.text)
        content = self.audit_path.read_text(encoding="utf-8")
        record = json.loads(content.splitlines()[0])
        self.assertEqual(record["action"], "suggestion_edited")
        self.assertEqual(record["selected_codes"], ["C5-11"])

    def test_rejected_creates_audit_entry(self) -> None:
        r = self.client.patch(
            "/api/v1/suggestions/sugg_003/review",
            json=self._body("rejected"),
        )
        self.assertEqual(r.status_code, 200, r.text)
        content = self.audit_path.read_text(encoding="utf-8")
        record = json.loads(content.splitlines()[0])
        self.assertEqual(record["action"], "suggestion_rejected")

    def test_free_text_only_hashed(self) -> None:
        secret_text = "FREE_TEXT_SENSIBLE_NO_DEBE_APARECER"
        r = self.client.patch(
            "/api/v1/suggestions/sugg_ft/review",
            json=self._body("accepted", free_text=secret_text, selected_codes=[]),
        )
        self.assertEqual(r.status_code, 200, r.text)
        content = self.audit_path.read_text(encoding="utf-8")
        self.assertNotIn(secret_text, content)
        record = json.loads(content.splitlines()[0])
        self.assertIn("free_text_hash", record["extra"])
        self.assertTrue(record["extra"]["has_free_text"])

    def test_evidence_not_stored_in_clear(self) -> None:
        evidence = "PII_NO_DEBE_ESTAR_EN_DISCO"
        r = self.client.patch(
            "/api/v1/suggestions/sugg_ev/review",
            json=self._body("accepted", evidence=evidence),
        )
        self.assertEqual(r.status_code, 200, r.text)
        content = self.audit_path.read_text(encoding="utf-8")
        self.assertNotIn(evidence, content)

    def test_invalid_decision_returns_422(self) -> None:
        r = self.client.patch(
            "/api/v1/suggestions/sugg_x/review",
            json=self._body("approved"),  # no esta en enum
        )
        self.assertEqual(r.status_code, 422)

    def test_missing_user_id_returns_422(self) -> None:
        body = self._body("accepted")
        body.pop("user_id")
        r = self.client.patch(
            "/api/v1/suggestions/sugg_x/review",
            json=body,
        )
        self.assertEqual(r.status_code, 422)

    def test_no_audit_configured_returns_503(self) -> None:
        os.environ.pop("AUDIT_HMAC_KEY", None)
        routes_audit._get_audit_log.cache_clear()

        r = self.client.patch(
            "/api/v1/suggestions/sugg_x/review",
            json=self._body("accepted"),
        )
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
