from __future__ import annotations

import time
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402


class JobsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_create_and_get_noop_job(self) -> None:
        created = self.client.post(
            "/api/v1/jobs",
            json={"kind": "noop", "payload": {"x": 1}},
        )
        self.assertEqual(created.status_code, 200)
        job_id = created.json()["id"]

        payload = None
        for _ in range(20):
            fetched = self.client.get(f"/api/v1/jobs/{job_id}")
            self.assertEqual(fetched.status_code, 200)
            payload = fetched.json()
            if payload["status"] == "completed":
                break
            time.sleep(0.02)

        assert payload is not None
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["result"], {"ok": True, "echo": {"x": 1}})

    def test_unknown_kind_returns_400(self) -> None:
        response = self.client.post(
            "/api/v1/jobs",
            json={"kind": "missing", "payload": {}},
        )

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
