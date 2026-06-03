"""Endpoints v1 de sesiones de entrevista (Hito persistencia).

Una sesion agrupa las sugerencias producidas durante una grabacion de
entrevista libre. El flujo real: el medico abre el micro y entrevista sin
ceñirse a una seccion; la extraccion corre sobre el modulo completo y las
sugerencias resultantes se asocian a la sesion (no a una seccion).

Requiere persistencia activa (`PERSISTENCE_ENABLED=true`). Si esta desactivada,
los endpoints responden 503.

POST /api/v1/sessions               -> crea sesion
GET  /api/v1/sessions/{id}          -> sesion + sugerencias persistidas
POST /api/v1/sessions/{id}/close    -> cierra sesion
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_app_settings, get_persistence_store
from app.api.security import enforce_internal_api_key, internal_api_key_header
from app.core.config import Settings
from app.services.persistence import PersistenceStore


router = APIRouter()


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    module: Literal["history", "exam"]


def _store_or_503(store: PersistenceStore | None) -> PersistenceStore:
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="Persistencia desactivada: requiere PERSISTENCE_ENABLED=true",
        )
    return store


def persist_suggestions(
    store: PersistenceStore | None,
    session_id: str | None,
    suggestions: list,
) -> list[str]:
    """Guarda sugerencias en la sesion si procede.

    No-op si no hay session_id o la persistencia esta desactivada. Si se pasa un
    session_id que no existe, 404 (evita huerfanas). Devuelve ids persistidos.
    """
    if not session_id or store is None:
        return []
    if store.get_session(session_id) is None:
        raise HTTPException(
            status_code=404, detail=f"Sesion no encontrada: {session_id}"
        )
    return store.save_suggestions(session_id=session_id, suggestions=suggestions)


@router.post("/sessions")
def create_session(
    request: CreateSessionRequest,
    settings: Settings = Depends(get_app_settings),
    store: PersistenceStore | None = Depends(get_persistence_store),
    internal_api_key: str | None = Depends(internal_api_key_header),
) -> dict[str, Any]:
    enforce_internal_api_key(settings, internal_api_key)
    db = _store_or_503(store)
    return db.create_session(
        patient_id=request.patient_id,
        user_id=request.user_id,
        module=request.module,
    )


@router.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    settings: Settings = Depends(get_app_settings),
    store: PersistenceStore | None = Depends(get_persistence_store),
    internal_api_key: str | None = Depends(internal_api_key_header),
) -> dict[str, Any]:
    enforce_internal_api_key(settings, internal_api_key)
    db = _store_or_503(store)
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Sesion no encontrada")
    session["suggestions"] = db.get_suggestions(session_id)
    return session


@router.post("/sessions/{session_id}/close")
def close_session(
    session_id: str,
    settings: Settings = Depends(get_app_settings),
    store: PersistenceStore | None = Depends(get_persistence_store),
    internal_api_key: str | None = Depends(internal_api_key_header),
) -> dict[str, Any]:
    enforce_internal_api_key(settings, internal_api_key)
    db = _store_or_503(store)
    if db.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Sesion no encontrada")
    closed = db.close_session(session_id)
    return {"ok": True, "session_id": session_id, "closed": closed}


__all__ = ["router", "CreateSessionRequest"]
