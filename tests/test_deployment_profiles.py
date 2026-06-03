from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings  # noqa: E402


class DeploymentProfilesTest(unittest.TestCase):
    def test_demo_defaults_allow_cache_and_debug(self) -> None:
        with patch.dict(os.environ, {"DEPLOYMENT_PROFILE": "demo"}, clear=True):
            settings = Settings()

        self.assertEqual(settings.deployment_profile, "demo")
        self.assertFalse(settings.local_only)
        self.assertTrue(settings.audio_cache_enabled)
        self.assertTrue(settings.debug_transcripts)

    def test_prototype_local_derives_local_only_and_cache_off(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DEPLOYMENT_PROFILE": "prototype_local",
                "IA_PROVIDER": "cloudflare",
            },
            clear=True,
        ):
            settings = Settings()

        self.assertEqual(settings.deployment_profile, "prototype_local")
        self.assertTrue(settings.local_only)
        self.assertFalse(settings.audio_cache_enabled)
        self.assertFalse(settings.debug_transcripts)
        self.assertEqual(settings.ia_provider, "heuristic")

    def test_explicit_cache_env_overrides_profile_default(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DEPLOYMENT_PROFILE": "prototype_local",
                "AUDIO_CACHE_ENABLED": "true",
            },
            clear=True,
        ):
            settings = Settings()

        self.assertTrue(settings.audio_cache_enabled)

    def test_invalid_profile_falls_back_to_demo(self) -> None:
        with patch.dict(os.environ, {"DEPLOYMENT_PROFILE": "bogus"}, clear=True):
            settings = Settings()

        self.assertEqual(settings.deployment_profile, "demo")


if __name__ == "__main__":
    unittest.main()
