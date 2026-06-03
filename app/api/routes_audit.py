"""Endpoints v1 de audit log (Hito 11).

POST /api/v1/audit/events       → registra evento (suggestion accepted/edited/rejected/...).
GET  /api/v1/audit/verify       → verifica integridad de la cadena HMAC.
GET  /api/v1/audit/events?n=N   → lista las ultimas N entradas (metadata + hashes, no PHI).

Todos requieren `INTERNAL_API_KEY` fuera de `demo`. En `demo` se permite sin auth
para facilitar pruebas locales, pero el archivo destino del audit_log puede
desactivarse poniendo `AUDIT_LOG_PATH=""` (path vacio).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_app_settings
from app.api.security import enforce_internal_api_key, internal_api_key_header
from app.core.config import Settings
from app.services.audit_log import AuditAction, AuditEntry, AuditLog, hash_evidence
import os


router = APIRouter()


# --- Pydantic request models -------------------------------------------------


class AuditEventRequest(BaseModel):
    """Cuerpo del POST /api/v1/audit/events.

    `evidence` es opcional. Si se pasa, solo se almacena su SHA-256 (no PHI).
    """

    model_config = ConfigDict(extra="forbid")

    action: Literal[
        "suggestion_proposed",
        "suggestion_accepted",
        "suggestion_edited",
        "suggestion_rejected",
        "session_started",
        "session_closed",
    ]
    user_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    question_id: str = ""
    selected_codes: list[str] = Field(default_factory=list)
    evidence: str = ""        # plano, se hashea antes de persistir
    confidence: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


# --- Singleton AuditLog ------------------------------------------------------


@lru_cache(maxsize=1)
def _get_audit_log() -> AuditLog | None:
    """Carga AuditLog desde env:

    - `AUDIT_LOG_PATH`: ruta del archivo activo (default `audit.log.jsonl`).
    - `AUDIT_HMAC_KEY`: secreto HMAC (obligatorio; sin este, audit desactivado).
    - `AUDIT_MAX_SIZE_BYTES`: rotacion automatica si > 0 (default 0 = sin rotacion).
    - `AUDIT_ARCHIVE_DIR`: destino archivado (default `<path_parent>/archive`).
    - `AUDIT_ENCRYPT_ARCHIVED`: `true` para cifrar archivados con Fernet.
    - `AUDIT_ENCRYPT_KEY`: clave Fernet (urlsafe-b64 32 bytes) o passphrase
      arbitraria (se deriva via SHA-256). Obligatoria si encrypt activo.
    """
    path = os.getenv("AUDIT_LOG_PATH", "audit.log.jsonl").strip()
    if not path:
        return None  # explicitamente desactivado
    secret = os.getenv("AUDIT_HMAC_KEY", "").strip()
    if not secret:
        return None  # sin secreto, audit desactivado
    encrypt_flag = os.getenv("AUDIT_ENCRYPT_ARCHIVED", "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        return AuditLog(
            path=path,
            secret_key=secret,
            max_size_bytes=int(os.getenv("AUDIT_MAX_SIZE_BYTES", "0")),
            archive_dir=os.getenv("AUDIT_ARCHIVE_DIR") or None,
            encrypt_archived=encrypt_flag,
            encrypt_key=os.getenv("AUDIT_ENCRYPT_KEY") or None,
        )
    except Exception:  # noqa: BLE001
        return None


def _audit_or_503() -> AuditLog:
    log = _get_audit_log()
    if log is None:
        raise HTTPException(
            status_code=503,
            detail="Audit log no configurado: requiere AUDIT_LOG_PATH y AUDIT_HMAC_KEY",
        )
    return log


# --- Endpoints ---------------------------------------------------------------


@router.post("/events")
def append_event(
    request: AuditEventRequest,
    settings: Settings = Depends(get_app_settings),
    internal_api_key: str | None = Depends(internal_api_key_header),
) -> dict[str, Any]:
    """Anade un evento al audit log encadenado."""
    enforce_internal_api_key(settings, internal_api_key)
    log = _audit_or_503()

    from datetime import datetime, timezone

    entry = AuditEntry(
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        action=request.action,  # type: ignore[arg-type]
        user_id=request.user_id,
        patient_id=request.patient_id,
        question_id=request.question_id,
        selected_codes=list(request.selected_codes),
        evidence_hash=hash_evidence(request.evidence) if request.evidence else "",
        confidence=request.confidence,
        extra=request.extra,
    )
    record = log.append(entry)
    # Eliminar campos PHI-adjacentes si el cliente quiere usar el record
    return {
        "ok": True,
        "chain_hmac": record["chain_hmac"],
        "prev_chain_hmac": record["prev_chain_hmac"],
        "timestamp_utc": record["timestamp_utc"],
    }


@router.get("/verify")
def verify_chain(
    settings: Settings = Depends(get_app_settings),
    internal_api_key: str | None = Depends(internal_api_key_header),
) -> dict[str, Any]:
    """Recalcula la cadena HMAC y reporta integridad."""
    enforce_internal_api_key(settings, internal_api_key)
    log = _audit_or_503()
    ok, n, err = log.verify_chain()
    return {
        "ok": ok,
        "n_entries": n,
        "error": err,
    }


@router.get("/events")
def list_events(
    n: int = 50,
    settings: Settings = Depends(get_app_settings),
    internal_api_key: str | None = Depends(internal_api_key_header),
) -> dict[str, Any]:
    """Devuelve las ultimas N entradas (metadata + hashes, sin PHI)."""
    enforce_internal_api_key(settings, internal_api_key)
    log = _audit_or_503()
    if n <= 0 or n > 1000:
        raise HTTPException(status_code=400, detail="n debe estar en [1, 1000]")

    path = Path(log.path)
    if not path.exists() or path.stat().st_size == 0:
        return {"entries": [], "total": 0}

    lines = path.read_text(encoding="utf-8").splitlines()
    lines = [l for l in lines if l.strip()]
    last = lines[-n:]
    parsed = []
    for raw in last:
        try:
            parsed.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return {"entries": parsed, "total": len(lines)}


__all__ = ["router", "AuditEventRequest"]
