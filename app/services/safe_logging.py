from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


SENSITIVE_KEY_MARKERS = ("TOKEN", "KEY", "SECRET", "PASSWORD", "TRANSCRIPT", "EVIDENCE")
MAX_TEXT_VALUE = 80


def sanitize_for_log(value: Any) -> Any:
    """Redacta estructuras antes de enviarlas a logs operativos."""
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                sanitized[key_text] = _redacted_value(item)
            else:
                sanitized[key_text] = sanitize_for_log(item)
        return sanitized

    if isinstance(value, list):
        return [sanitize_for_log(item) for item in value]

    if isinstance(value, tuple):
        return tuple(sanitize_for_log(item) for item in value)

    if isinstance(value, str):
        return _truncate_and_scrub(value)

    return value


def safe_log_extra(**kwargs: Any) -> dict[str, Any]:
    return sanitize_for_log(kwargs)


def _is_sensitive_key(key: str) -> bool:
    upper = key.upper()
    return any(marker in upper for marker in SENSITIVE_KEY_MARKERS)


def _redacted_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    return "<redacted>"


def _truncate_and_scrub(value: str) -> str:
    scrubbed = re.sub(
        r"(?i)(token|api[_-]?key|password|secret)\s*[:=]\s*['\"]?[^'\"\s]+",
        r"\1=<redacted>",
        value,
    )
    if len(scrubbed) <= MAX_TEXT_VALUE:
        return scrubbed
    return scrubbed[: MAX_TEXT_VALUE - 3].rstrip() + "..."
