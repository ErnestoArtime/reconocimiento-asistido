from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.safe_logging import sanitize_for_log, safe_log_extra  # noqa: E402


class SafeLoggingTest(unittest.TestCase):
    def test_redacts_secret_keys(self) -> None:
        payload = sanitize_for_log(
            {
                "api_key": "abc123",
                "nested": {"cloudflare_token": "secret-token"},
            }
        )

        self.assertEqual(payload["api_key"], "<redacted>")
        self.assertEqual(payload["nested"]["cloudflare_token"], "<redacted>")

    def test_redacts_transcript_and_evidence_keys(self) -> None:
        payload = sanitize_for_log(
            {
                "transcript": "paciente con datos clinicos extensos",
                "suggestion": {"evidence": "no fuma actualmente"},
            }
        )

        self.assertEqual(payload["transcript"], "<redacted>")
        self.assertEqual(payload["suggestion"]["evidence"], "<redacted>")

    def test_truncates_long_free_text_values(self) -> None:
        payload = sanitize_for_log({"message": "x" * 200})

        self.assertLessEqual(len(payload["message"]), 80)
        self.assertTrue(payload["message"].endswith("..."))

    def test_scrubs_inline_secret_patterns(self) -> None:
        payload = sanitize_for_log({"message": "token=abc123 listo"})

        self.assertEqual(payload["message"], "token=<redacted> listo")

    def test_safe_log_extra_returns_sanitized_dict(self) -> None:
        payload = safe_log_extra(provider="heuristic", transcript="texto clinico")

        self.assertEqual(payload["provider"], "heuristic")
        self.assertEqual(payload["transcript"], "<redacted>")


if __name__ == "__main__":
    unittest.main()
