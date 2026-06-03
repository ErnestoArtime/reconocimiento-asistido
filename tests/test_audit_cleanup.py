"""Tests del script de retencion audit_cleanup."""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Importamos directo el modulo para no tocar argv
import audit_cleanup  # noqa: E402


class FindArchivedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make(self, name: str, mtime_offset_days: float = 0.0) -> Path:
        path = self.dir / name
        path.write_text("{}\n", encoding="utf-8")
        if mtime_offset_days:
            ts = time.time() - (mtime_offset_days * 86400)
            os.utime(path, (ts, ts))
        return path

    def test_finds_audit_files(self) -> None:
        self._make("audit-20260101000000-abc123.jsonl")
        self._make("audit-20260102000000-def456.jsonl")
        self._make("other-file.txt")  # NO se cuenta
        files = audit_cleanup.find_archived_files(self.dir)
        self.assertEqual(len(files), 2)
        self.assertTrue(all(f.name.startswith("audit-") for f in files))

    def test_nonexistent_dir_returns_empty(self) -> None:
        files = audit_cleanup.find_archived_files(Path("/nonexistent_xyz_12345"))
        self.assertEqual(files, [])

    def test_stale_files_filter(self) -> None:
        fresh = self._make("audit-fresh.jsonl", mtime_offset_days=1)
        old = self._make("audit-old.jsonl", mtime_offset_days=400)
        files = [fresh, old]

        stale = audit_cleanup.stale_files(files, retention_days=365)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0].name, "audit-old.jsonl")

    def test_zero_retention_returns_empty(self) -> None:
        f = self._make("audit-x.jsonl", mtime_offset_days=1000)
        stale = audit_cleanup.stale_files([f], retention_days=0)
        self.assertEqual(stale, [])

    def test_retention_boundary(self) -> None:
        # Archivo justo en el limite (1d antes que cutoff por margen seguro)
        on_edge = self._make("audit-edge.jsonl", mtime_offset_days=29.5)
        fresh = self._make("audit-fresh.jsonl", mtime_offset_days=1)

        stale_30 = audit_cleanup.stale_files([on_edge, fresh], retention_days=30)
        self.assertEqual(stale_30, [])

        stale_28 = audit_cleanup.stale_files([on_edge, fresh], retention_days=28)
        self.assertEqual([f.name for f in stale_28], ["audit-edge.jsonl"])


if __name__ == "__main__":
    unittest.main()
