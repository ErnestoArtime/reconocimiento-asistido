"""Cache de resultados de transcripcion por hash de audio + modelo.

Evita re-transcribir el mismo audio. Util en QA, repeticiones y benchmark.
Almacena JSON con TranscriptResult serializado.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from pathlib import Path

from app.services.audio.base import Segment, TranscriptResult


logger = logging.getLogger(__name__)


def hash_file(path: str | Path, extra: str = "") -> str:
    """SHA-256 del contenido + clave extra (provider+modelo+lang+prompt)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    if extra:
        h.update(b"||")
        h.update(extra.encode("utf-8"))
    return h.hexdigest()


def _entry_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.json"


def load(cache_dir: Path, key: str) -> TranscriptResult | None:
    path = _entry_path(cache_dir, key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        segments = [Segment(**s) for s in data.get("segments", [])]
        return TranscriptResult(
            text=data["text"],
            segments=segments,
            language=data.get("language", "es"),
            duration_s=data.get("duration_s", 0.0),
            rtf=data.get("rtf", 0.0),
            provider=data.get("provider", ""),
            model=data.get("model", ""),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cache corrupta en %s: %s", path, exc)
        return None


def save(cache_dir: Path, key: str, result: TranscriptResult) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "text": result.text,
        "language": result.language,
        "duration_s": result.duration_s,
        "rtf": result.rtf,
        "provider": result.provider,
        "model": result.model,
        "segments": [asdict(s) for s in result.segments],
    }
    _entry_path(cache_dir, key).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
