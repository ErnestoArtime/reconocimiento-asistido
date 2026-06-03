"""Endpoints v1 para registrar decisiones de revision humana (Hito V3).

Cada decision (`accepted`/`edited`/`rejected`) se registra automaticamente en
el audit log encadenado (huella auditable primaria). Si la persistencia esta
activa (`PERSISTENCE_ENABLED=true`) y el `suggestion_id` existe en el store,
tambien se actualiza el `review_status` de la sugerencia y se inserta una fila
en `reviews`. Con persistencia desactivada solo se registra el audit.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_app_settings, get_persistence_store
from app.api.routes_audit import _get_audit_log
from app.api.security import enforce_internal_api_key, internal_api_key_header
from app.core.config import Settings
from app.services.audit_log import AuditEntry, hash_evidence
from app.services.persistence import PersistenceStore


router = APIRouter()


ReviewDecision = Literal["accepted", "edited", "rejected"]


class ReviewRequest(BaseModel):
    """Decision humana sobre una sugerencia."""

    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    user_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    selected_codes: list[str] = Field(default_factory=list)
    evidence: str = ""
    confidence: float | None = None
    free_text: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


_DECISION_TO_ACTION = {
    "accepted": "suggestion_accepted",
    "edited": "suggestion_edited",
    "rejected": "suggestion_rejected",
}


@router.patch("/suggestions/{suggestion_id}/review")
def review_suggestion(
    suggestion_id: str,
    request: ReviewRequest,
    settings: Settings = Depends(get_app_settings),
    store: PersistenceStore | None = Depends(get_persistence_store),
    internal_api_key: str | None = Depends(internal_api_key_header),
) -> dict[str, Any]:
    """Registra decision humana sobre una sugerencia + audit hook automatico.

    El `suggestion_id` debe ser el id persistido (UUID de la tabla
    `suggestions`, visible en GET /api/v1/sessions/{id}). Se guarda tambien en
    `extra.suggestion_id` para trazar el evento al registro UI.
    """
    enforce_internal_api_key(settings, internal_api_key)

    audit = _get_audit_log()
    if audit is None:
        raise HTTPException(
            status_code=503,
            detail="Audit log no configurado: requiere AUDIT_LOG_PATH y AUDIT_HMAC_KEY",
        )

    action = _DECISION_TO_ACTION[request.decision]
    extra = dict(request.extra or {})
    extra["suggestion_id"] = suggestion_id
    if request.free_text:
        # No exponer texto libre en audit; solo hash + flag presencia.
        extra["free_text_hash"] = hash_evidence(request.free_text)
        extra["has_free_text"] = True

    entry = AuditEntry(
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        action=action,  # type: ignore[arg-type]
        user_id=request.user_id,
        patient_id=request.patient_id,
        question_id=request.question_id,
        selected_codes=list(request.selected_codes),
        evidence_hash=hash_evidence(request.evidence) if request.evidence else "",
        confidence=request.confidence,
        extra=extra,
    )
    record = audit.append(entry)

    persisted = False
    if store is not None:
        persisted = store.update_review(
            suggestion_id=suggestion_id,
            decision=request.decision,
            user_id=request.user_id,
            patient_id=request.patient_id,
            selected_codes=request.selected_codes,
            free_text=request.free_text,
            confidence=request.confidence,
            chain_hmac=record["chain_hmac"],
        )

    return {
        "ok": True,
        "suggestion_id": suggestion_id,
        "decision": request.decision,
        "persisted": persisted,
        "chain_hmac": record["chain_hmac"],
        "timestamp_utc": record["timestamp_utc"],
    }


__all__ = ["router", "ReviewRequest"]
