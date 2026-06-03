from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings  # noqa: E402
from app.services.audio.base import TranscriptResult  # noqa: E402
from app.services.audio.transcription_service import transcribe_upload  # noqa: E402


class LocalOnlyProfileTest(unittest.TestCase):
    def test_transcription_cache_disabled_by_profile(self) -> None:
        provider = Mock()
        provider.transcribe.return_value = TranscriptResult(
            text="audio transcrito",
            provider="fake",
            model="fake-model",
        )

        with patch.dict(
            os.environ,
            {
                "DEPLOYMENT_PROFILE": "prototype_local",
                "AUDIO_PROVIDER": "fake",
                "AUDIO_FALLBACK_PROVIDER": "fake",
            },
            clear=True,
        ):
            settings = Settings()

        with (
            patch("app.services.audio.transcription_service.normalize_audio") as normalize_audio,
            patch("app.services.audio.transcription_service.registry.get_provider", return_value=provider),
            patch("app.services.audio.transcription_service.cache.hash_file") as hash_file,
            patch("app.services.audio.transcription_service.cache.load") as cache_load,
            patch("app.services.audio.transcription_service.cache.save") as cache_save,
        ):
            normalize_audio.side_effect = lambda _raw, wav_path, **_kwargs: Path(wav_path).write_bytes(b"wav")
            result = transcribe_upload(
                raw_bytes=b"audio",
                filename="sample.wav",
                settings=settings,
                use_cache=True,
            )

        self.assertEqual(result.text, "audio transcrito")
        hash_file.assert_not_called()
        cache_load.assert_not_called()
        cache_save.assert_not_called()

    def test_transcription_cache_enabled_in_demo(self) -> None:
        provider = Mock()
        provider.transcribe.return_value = TranscriptResult(
            text="audio transcrito",
            provider="fake",
            model="fake-model",
        )

        with patch.dict(
            os.environ,
            {
                "DEPLOYMENT_PROFILE": "demo",
                "AUDIO_PROVIDER": "fake",
                "AUDIO_FALLBACK_PROVIDER": "fake",
            },
            clear=True,
        ):
            settings = Settings()

        with (
            patch("app.services.audio.transcription_service.normalize_audio") as normalize_audio,
            patch("app.services.audio.transcription_service.registry.get_provider", return_value=provider),
            patch("app.services.audio.transcription_service.cache.hash_file", return_value="abc") as hash_file,
            patch("app.services.audio.transcription_service.cache.load", return_value=None) as cache_load,
            patch("app.services.audio.transcription_service.cache.save") as cache_save,
        ):
            normalize_audio.side_effect = lambda _raw, wav_path, **_kwargs: Path(wav_path).write_bytes(b"wav")
            result = transcribe_upload(
                raw_bytes=b"audio",
                filename="sample.wav",
                settings=settings,
                use_cache=True,
            )

        self.assertEqual(result.text, "audio transcrito")
        hash_file.assert_called_once()
        cache_load.assert_called_once()
        cache_save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
