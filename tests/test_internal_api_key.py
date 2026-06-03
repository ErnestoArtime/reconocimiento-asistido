from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api.security import enforce_internal_api_key  # noqa: E402
from app.core.config import Settings  # noqa: E402


class InternalApiKeyTest(unittest.TestCase):
    def test_demo_does_not_require_key(self) -> None:
        with patch.dict(os.environ, {"DEPLOYMENT_PROFILE": "demo"}, clear=True):
            settings = Settings()

        enforce_internal_api_key(settings, None)

    def test_local_profile_requires_configured_key(self) -> None:
        with patch.dict(
            os.environ,
            {"DEPLOYMENT_PROFILE": "prototype_local"},
            clear=True,
        ):
            settings = Settings()

        with self.assertRaises(HTTPException) as ctx:
            enforce_internal_api_key(settings, None)

        self.assertEqual(ctx.exception.status_code, 503)

    def test_local_profile_rejects_wrong_key(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DEPLOYMENT_PROFILE": "prototype_local",
                "INTERNAL_API_KEY": "expected",
            },
            clear=True,
        ):
            settings = Settings()

        with self.assertRaises(HTTPException) as ctx:
            enforce_internal_api_key(settings, "wrong")

        self.assertEqual(ctx.exception.status_code, 401)

    def test_local_profile_accepts_matching_key(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DEPLOYMENT_PROFILE": "production",
                "INTERNAL_API_KEY": "expected",
            },
            clear=True,
        ):
            settings = Settings()

        enforce_internal_api_key(settings, "expected")


if __name__ == "__main__":
    unittest.main()
