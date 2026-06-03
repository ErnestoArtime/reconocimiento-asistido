from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_app_settings
from app.api.security import enforce_internal_api_key, internal_api_key_header
from app.core.config import Settings
from app.services.job_queue import job_queue


router = APIRouter()


class JobCreateRequest(BaseModel):
    kind: str = Field(default="noop")
    payload: dict[str, Any] = Field(default_factory=dict)


async def _noop_handler(payload: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(0)
    return {"ok": True, "echo": payload}


job_queue.register_handler("noop", _noop_handler)


@router.post("/jobs")
async def create_job(
    request: JobCreateRequest,
    settings: Settings = Depends(get_app_settings),
    internal_api_key: str | None = Depends(internal_api_key_header),
) -> dict[str, Any]:
    enforce_internal_api_key(settings, internal_api_key)
    try:
        job = await job_queue.submit(request.kind, request.payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job.to_dict()


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    settings: Settings = Depends(get_app_settings),
    internal_api_key: str | None = Depends(internal_api_key_header),
) -> dict[str, Any]:
    enforce_internal_api_key(settings, internal_api_key)
    job = job_queue.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job no encontrado")
    return job.to_dict()


@router.get("/jobs")
def list_jobs(
    settings: Settings = Depends(get_app_settings),
    internal_api_key: str | None = Depends(internal_api_key_header),
) -> dict[str, Any]:
    enforce_internal_api_key(settings, internal_api_key)
    return {"jobs": [job.to_dict() for job in job_queue.list_recent()]}
