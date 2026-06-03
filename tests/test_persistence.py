from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api import deps  # noqa: E402
from app.main import app  # noqa: E402
from app.models.extraction_contract import SuggestionV1  # noqa: E402
from app.services.persistence import PersistenceStore  # noqa: E402


def _suggestion(question_id: str, code: str, review="pending") -> SuggestionV1:
    return SuggestionV1(
        question_id=question_id,
        selected_codes=[code],
        selected_labels=["Si"],
        confidence=0.8,
        evidence="evidencia corta",
        review_status=review,
    )


class PersistenceStoreUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = PersistenceStore(Path(self._tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def test_session_lifecycle(self) -> None:
        session = self.store.create_session(
            patient_id="P1", user_id="dr.house", module="exam"
        )
        self.assertEqual(session["status"], "open")
        fetched = self.store.get_session(session["id"])
        self.assertEqual(fetched["patient_id"], "P1")
        self.assertTrue(self.store.close_session(session["id"]))
        self.assertEqual(self.store.get_session(session["id"])["status"], "closed")
        # cerrar dos veces no vuelve a marcar
        self.assertFalse(self.store.close_session(session["id"]))

    def test_save_and_get_suggestions(self) -> None:
        session = self.store.create_session(patient_id="P1", user_id="u", module="exam")
        ids = self.store.save_suggestions(
            session_id=session["id"],
            suggestions=[_suggestion("E1-1", "S"), _suggestion("E1-2", "N")],
        )
        self.assertEqual(len(ids), 2)
        rows = self.store.get_suggestions(session["id"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["selected_codes"], ["S"])
        self.assertEqual(rows[0]["review_status"], "pending")

    def test_resave_replaces_pending_keeps_reviewed(self) -> None:
        session = self.store.create_session(patient_id="P1", user_id="u", module="exam")
        [sid] = self.store.save_suggestions(
            session_id=session["id"], suggestions=[_suggestion("E1-1", "S")]
        )
        # revisar (acepta) la sugerencia
        self.store.update_review(
            suggestion_id=sid, decision="accepted", user_id="u", patient_id="P1"
        )
        # re-extraer la misma pregunta NO debe pisar la ya revisada
        ids2 = self.store.save_suggestions(
            session_id=session["id"], suggestions=[_suggestion("E1-1", "N")]
        )
        self.assertEqual(ids2, [sid])
        row = self.store.get_suggestion(sid)
        self.assertEqual(row["review_status"], "accepted")
        self.assertEqual(row["selected_codes"], ["S"])  # se conservo

    def test_update_review_unknown_suggestion_returns_false(self) -> None:
        ok = self.store.update_review(
            suggestion_id="no-existe", decision="rejected", user_id="u", patient_id="P1"
        )
        self.assertFalse(ok)


class PersistenceApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = PersistenceStore(Path(self._tmp.name) / "api.db")
        app.dependency_overrides[deps.get_persistence_store] = lambda: self.store
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(deps.get_persistence_store, None)
        self.store.close()
        self._tmp.cleanup()

    def test_create_get_close_session(self) -> None:
        created = self.client.post(
            "/api/v1/sessions",
            json={"patient_id": "P1", "user_id": "u", "module": "exam"},
        )
        self.assertEqual(created.status_code, 200)
        sid = created.json()["id"]

        got = self.client.get(f"/api/v1/sessions/{sid}")
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["suggestions"], [])

        closed = self.client.post(f"/api/v1/sessions/{sid}/close")
        self.assertEqual(closed.status_code, 200)
        self.assertTrue(closed.json()["closed"])

    def test_extraction_with_session_id_persists_suggestions(self) -> None:
        sid = self.client.post(
            "/api/v1/sessions",
            json={"patient_id": "P1", "user_id": "u", "module": "exam"},
        ).json()["id"]

        resp = self.client.post(
            "/api/v1/ia/extract-from-text",
            json={
                "module": "exam",
                "text": (
                    "Cuero cabelludo normal. Cara normal. Boca normal. "
                    "Oidos normales. Ojos normales. Nariz normal."
                ),
                "ia_provider": "heuristic",
                "session_id": sid,
            },
        )
        self.assertEqual(resp.status_code, 200)
        stored = self.client.get(f"/api/v1/sessions/{sid}").json()["suggestions"]
        self.assertTrue(stored, "esperaba sugerencias persistidas en la sesion")

    def test_extraction_with_unknown_session_id_404(self) -> None:
        resp = self.client.post(
            "/api/v1/ia/extract-from-text",
            json={
                "module": "exam",
                "text": "Boca normal.",
                "ia_provider": "heuristic",
                "session_id": "no-existe",
            },
        )
        self.assertEqual(resp.status_code, 404)

    def test_session_endpoints_503_when_persistence_disabled(self) -> None:
        app.dependency_overrides[deps.get_persistence_store] = lambda: None
        resp = self.client.post(
            "/api/v1/sessions",
            json={"patient_id": "P1", "user_id": "u", "module": "exam"},
        )
        self.assertEqual(resp.status_code, 503)


if __name__ == "__main__":
    unittest.main()
