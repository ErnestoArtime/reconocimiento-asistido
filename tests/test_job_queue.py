from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.job_queue import InMemoryJobQueue  # noqa: E402


class JobQueueTest(unittest.IsolatedAsyncioTestCase):
    async def test_job_completes(self) -> None:
        queue = InMemoryJobQueue()

        async def handler(payload: dict) -> dict:
            return {"value": payload["value"] + 1}

        queue.register_handler("inc", handler)
        job = await queue.submit("inc", {"value": 1})
        await asyncio.wait_for(queue._queue.join(), timeout=1)

        stored = queue.get(job.id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.status, "completed")
        self.assertEqual(stored.result, {"value": 2})
        await queue.stop()

    async def test_job_failure_is_recorded(self) -> None:
        queue = InMemoryJobQueue()

        async def handler(_payload: dict) -> dict:
            raise RuntimeError("boom")

        queue.register_handler("fail", handler)
        job = await queue.submit("fail", {})
        await asyncio.wait_for(queue._queue.join(), timeout=1)

        stored = queue.get(job.id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.status, "failed")
        self.assertEqual(stored.error, "boom")
        await queue.stop()

    async def test_unknown_job_kind_rejected(self) -> None:
        queue = InMemoryJobQueue()

        with self.assertRaises(ValueError):
            await queue.submit("missing", {})


if __name__ == "__main__":
    unittest.main()
