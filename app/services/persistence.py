"""Persistencia SQLite para sesiones, sugerencias y revisiones (Hito persistencia).

Decision de alcance (RGPD): se persisten SOLO sugerencias, revisiones y la
sesion que las agrupa. NO se guarda el audio ni el texto completo de la
transcripcion. El `evidence` de cada sugerencia (fragmento corto) si se guarda
porque es parte de la sugerencia auditable; el audit log encadenado sigue
guardando solo su hash.

Modelo centrado en SESION, no en seccion: una grabacion de entrevista libre
produce N sugerencias repartidas por varias secciones del modulo. Cada
sugerencia ya lleva su `question_id` (que implica su seccion).

SQLite con WAL + lock de proceso para uso multi-hilo del servidor.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.extraction_contract import SuggestionV1


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    patient_id  TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    module      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  TEXT NOT NULL,
    closed_at   TEXT
);

CREATE TABLE IF NOT EXISTS suggestions (
    id               TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL REFERENCES sessions(id),
    question_id      TEXT NOT NULL,
    module           TEXT NOT NULL DEFAULT '',
    section          TEXT NOT NULL DEFAULT '',
    selected_codes   TEXT NOT NULL DEFAULT '[]',
    selected_labels  TEXT NOT NULL DEFAULT '[]',
    free_text        TEXT,
    confidence       REAL NOT NULL DEFAULT 0,
    evidence         TEXT NOT NULL DEFAULT '',
    audio_start      REAL,
    audio_end        REAL,
    speaker          TEXT,
    technical_status TEXT NOT NULL DEFAULT 'valid',
    review_status    TEXT NOT NULL DEFAULT 'pending',
    risk_flags       TEXT NOT NULL DEFAULT '[]',
    reason           TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_suggestions_session ON suggestions(session_id);

CREATE TABLE IF NOT EXISTS reviews (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    suggestion_id  TEXT NOT NULL,
    decision       TEXT NOT NULL,
    user_id        TEXT NOT NULL,
    patient_id     TEXT NOT NULL,
    selected_codes TEXT NOT NULL DEFAULT '[]',
    free_text      TEXT,
    confidence     REAL,
    chain_hmac     TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_suggestion ON reviews(suggestion_id);
"""


class PersistenceStore:
    """Store SQLite thread-safe. Una sola conexion compartida + lock."""

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        if self.path.parent and not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(self.path), check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- Sesiones -------------------------------------------------------------

    def create_session(self, *, patient_id: str, user_id: str, module: str) -> dict[str, Any]:
        session_id = str(uuid.uuid4())
        now = _now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (id, patient_id, user_id, module, status, created_at) "
                "VALUES (?, ?, ?, ?, 'open', ?)",
                (session_id, patient_id, user_id, module, now),
            )
            self._conn.commit()
        return {
            "id": session_id,
            "patient_id": patient_id,
            "user_id": user_id,
            "module": module,
            "status": "open",
            "created_at": now,
            "closed_at": None,
        }

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def close_session(self, session_id: str) -> bool:
        now = _now_iso()
        with self._lock:
            cur = self._conn.execute(
                "UPDATE sessions SET status = 'closed', closed_at = ? "
                "WHERE id = ? AND status = 'open'",
                (now, session_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    # --- Sugerencias ----------------------------------------------------------

    def save_suggestions(
        self, *, session_id: str, suggestions: list[SuggestionV1]
    ) -> list[str]:
        """Guarda sugerencias de una extraccion. Devuelve los ids generados.

        Idempotencia por sesion+pregunta: si ya existe una sugerencia para esa
        (session_id, question_id), se reemplaza (la ultima extraccion gana),
        salvo que la previa ya tenga decision humana (review_status != pending).
        """
        now = _now_iso()
        ids: list[str] = []
        with self._lock:
            for s in suggestions:
                existing = self._conn.execute(
                    "SELECT id, review_status FROM suggestions "
                    "WHERE session_id = ? AND question_id = ?",
                    (session_id, s.question_id),
                ).fetchone()
                if existing and existing["review_status"] != "pending":
                    # No pisar una sugerencia ya revisada por humano.
                    ids.append(existing["id"])
                    continue
                if existing:
                    self._conn.execute(
                        "DELETE FROM suggestions WHERE id = ?", (existing["id"],)
                    )
                sug_id = str(uuid.uuid4())
                self._conn.execute(
                    "INSERT INTO suggestions ("
                    "id, session_id, question_id, module, section, selected_codes, "
                    "selected_labels, free_text, confidence, evidence, audio_start, "
                    "audio_end, speaker, technical_status, review_status, risk_flags, "
                    "reason, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        sug_id,
                        session_id,
                        s.question_id,
                        getattr(s, "module", "") or "",
                        getattr(s, "section", "") or "",
                        json.dumps(s.selected_codes),
                        json.dumps(s.selected_labels),
                        s.free_text,
                        s.confidence,
                        s.evidence,
                        s.audio_start,
                        s.audio_end,
                        s.speaker,
                        s.technical_status,
                        s.review_status,
                        json.dumps(s.risk_flags),
                        s.reason,
                        now,
                        now,
                    ),
                )
                ids.append(sug_id)
            self._conn.commit()
        return ids

    def get_suggestions(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM suggestions WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            ).fetchall()
        return [_suggestion_row_to_dict(row) for row in rows]

    def get_suggestion(self, suggestion_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)
            ).fetchone()
        return _suggestion_row_to_dict(row) if row else None

    def update_review(
        self,
        *,
        suggestion_id: str,
        decision: str,
        user_id: str,
        patient_id: str,
        selected_codes: list[str] | None = None,
        free_text: str | None = None,
        confidence: float | None = None,
        chain_hmac: str | None = None,
    ) -> bool:
        """Actualiza review_status de la sugerencia + registra fila en reviews.

        Devuelve False si la sugerencia no existe en el store (p.ej. extraccion
        no se persistio). El audit log sigue siendo la huella primaria.
        """
        now = _now_iso()
        review_status = {
            "accepted": "accepted",
            "edited": "edited",
            "rejected": "rejected",
        }.get(decision, "pending")
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM suggestions WHERE id = ?", (suggestion_id,)
            ).fetchone()
            if exists:
                fields = ["review_status = ?", "updated_at = ?"]
                params: list[Any] = [review_status, now]
                if selected_codes is not None:
                    fields.append("selected_codes = ?")
                    params.append(json.dumps(selected_codes))
                if free_text is not None:
                    fields.append("free_text = ?")
                    params.append(free_text)
                params.append(suggestion_id)
                self._conn.execute(
                    f"UPDATE suggestions SET {', '.join(fields)} WHERE id = ?",
                    params,
                )
            self._conn.execute(
                "INSERT INTO reviews ("
                "suggestion_id, decision, user_id, patient_id, selected_codes, "
                "free_text, confidence, chain_hmac, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    suggestion_id,
                    decision,
                    user_id,
                    patient_id,
                    json.dumps(selected_codes or []),
                    free_text,
                    confidence,
                    chain_hmac,
                    now,
                ),
            )
            self._conn.commit()
            return bool(exists)


def _suggestion_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    for key in ("selected_codes", "selected_labels", "risk_flags"):
        try:
            data[key] = json.loads(data.get(key) or "[]")
        except (json.JSONDecodeError, TypeError):
            data[key] = []
    return data


__all__ = ["PersistenceStore"]
