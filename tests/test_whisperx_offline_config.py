from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings  # noqa: E402
from app.services.audio.providers.whisperx_provider import WhisperXProvider  # noqa: E402


class _FakeModel:
    pass


class _FakeDiarizationPipeline:
    calls = []

    def __init__(
        self,
        use_auth_token=None,
        device="cpu",
        model_name=None,
    ) -> None:
        self.calls.append(
            {
                "use_auth_token": use_auth_token,
                "device": device,
                "model_name": model_name,
            }
        )


class _FakeWhisperX:
    DiarizationPipeline = _FakeDiarizationPipeline

    @staticmethod
    def load_model(_model_size, _device, compute_type=None):
        return _FakeModel()


class WhisperXOfflineConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        _FakeDiarizationPipeline.calls.clear()

    def test_local_diarization_model_is_passed_to_pipeline(self) -> None:
        with patch.dict(sys.modules, {"whisperx": _FakeWhisperX}):
            provider = WhisperXProvider(
                model_size="base",
                device="cpu",
                compute_type="int8",
                hf_token=None,
                diarization_model="C:/models/pyannote",
                offline_mode=True,
                cache_dir="C:/models/huggingface",
            )
            provider._get_diarizer()

        self.assertEqual(_FakeDiarizationPipeline.calls[0]["model_name"], "C:/models/pyannote")
        self.assertEqual(_FakeDiarizationPipeline.calls[0]["device"], "cpu")
        self.assertEqual(os.environ["HF_HUB_OFFLINE"], "1")
        self.assertEqual(os.environ["TRANSFORMERS_OFFLINE"], "1")

    def test_settings_expose_offline_audio_fields(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AUDIO_MODEL_CACHE_DIR": "C:/models/huggingface",
                "AUDIO_OFFLINE_MODE": "true",
                "WHISPERX_DIARIZATION_MODEL": "C:/models/pyannote",
                "HF_TOKEN": "token",
            },
            clear=True,
        ):
            settings = Settings()

        self.assertEqual(settings.audio_model_cache_dir, "C:/models/huggingface")
        self.assertTrue(settings.audio_offline_mode)
        self.assertEqual(settings.whisperx_diarization_model, "C:/models/pyannote")
        self.assertEqual(settings.whisperx_hf_token, "token")


if __name__ == "__main__":
    unittest.main()
