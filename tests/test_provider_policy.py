from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings  # noqa: E402
from app.services.provider_policy import (  # noqa: E402
    enforce_audio_provider_allowed,
    enforce_ia_provider_allowed,
)


class ProviderPolicyTest(unittest.TestCase):
    def test_demo_allows_online_ia(self) -> None:
        with patch.dict(os.environ, {"DEPLOYMENT_PROFILE": "demo"}, clear=True):
            settings = Settings()

        enforce_ia_provider_allowed("cloudflare", settings)

    def test_local_profile_blocks_online_ia(self) -> None:
        with patch.dict(os.environ, {"DEPLOYMENT_PROFILE": "prototype_local"}, clear=True):
            settings = Settings()

        with self.assertRaises(HTTPException) as ctx:
            enforce_ia_provider_allowed("cloudflare", settings)

        self.assertEqual(ctx.exception.status_code, 403)

    def test_local_profile_blocks_online_audio(self) -> None:
        with patch.dict(os.environ, {"DEPLOYMENT_PROFILE": "production"}, clear=True):
            settings = Settings()

        with self.assertRaises(HTTPException) as ctx:
            enforce_audio_provider_allowed("deepgram", settings)

        self.assertEqual(ctx.exception.status_code, 403)

    def test_local_profile_allows_local_audio(self) -> None:
        with patch.dict(os.environ, {"DEPLOYMENT_PROFILE": "prototype_local"}, clear=True):
            settings = Settings()

        enforce_audio_provider_allowed("faster_whisper", settings)


if __name__ == "__main__":
    unittest.main()
