from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


JobStatus = Literal["queued", "running", "completed", "failed"]
JobHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class JobRecord:
    id: str
    kind: str
    status: JobStatus = "queued"
    payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: _now_iso())
    updated_at: str = field(default_factory=lambda: _now_iso())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "payload": self.payload,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class InMemoryJobQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._handlers: dict[str, JobHandler] = {}
        self._worker_task: asyncio.Task | None = None

    def register_handler(self, kind: str, handler: JobHandler) -> None:
        self._handlers[kind] = handler

    async def start(self) -> None:
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def submit(self, kind: str, payload: dict[str, Any]) -> JobRecord:
        if kind not in self._handlers:
            raise ValueError(f"Job kind no registrado: {kind}")
        await self.start()
        job = JobRecord(id=str(uuid.uuid4()), kind=kind, payload=payload)
        self._jobs[job.id] = job
        await self._queue.put(job.id)
        return job

    def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def list_recent(self, limit: int = 50) -> list[JobRecord]:
        return list(self._jobs.values())[-limit:]

    async def _worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            job = self._jobs[job_id]
            job.status = "running"
            job.updated_at = _now_iso()
            try:
                job.result = await self._handlers[job.kind](job.payload)
                job.status = "completed"
            except Exception as exc:  # noqa: BLE001
                job.error = str(exc)
                job.status = "failed"
            finally:
                job.updated_at = _now_iso()
                self._queue.task_done()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


job_queue = InMemoryJobQueue()
