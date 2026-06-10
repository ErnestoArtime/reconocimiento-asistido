from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings  # noqa: E402
from app.services.audio import registry  # noqa: E402


class AudioStreamingProviderTest(unittest.TestCase):
    def tearDown(self) -> None:
        registry.get_provider.cache_clear()
        registry.get_streaming_provider.cache_clear()

    def test_streaming_provider_uses_lightweight_decode_settings(self) -> None:
        seen = {}

        def build(settings):
            seen["model"] = settings.audio_model
            seen["beam_size"] = settings.audio_beam_size
            seen["vad_filter"] = settings.audio_vad_filter
            provider = Mock()
            provider.name = "fake"
            return provider

        with patch.dict(
            os.environ,
            {
                "DEPLOYMENT_PROFILE": "demo",
                "AUDIO_PROVIDER": "fake",
                "AUDIO_MODEL": "large-v3",
                "AUDIO_STREAM_PROVIDER": "fake",
                "AUDIO_STREAM_MODEL": "base",
                "AUDIO_BEAM_SIZE": "5",
                "AUDIO_VAD_FILTER": "true",
            },
            clear=True,
        ):
            settings = Settings()

        with (
            patch("app.services.audio.registry.get_settings", return_value=settings),
            patch.dict(registry._BUILDERS, {"fake": build}, clear=True),
        ):
            registry.get_streaming_provider("fake")

        self.assertEqual(seen["model"], "base")
        self.assertEqual(seen["beam_size"], 1)
        self.assertFalse(seen["vad_filter"])


if __name__ == "__main__":
    unittest.main()
