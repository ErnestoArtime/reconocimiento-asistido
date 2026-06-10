from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import cloudflare_smoke_test  # noqa: E402


def _settings(**overrides):
    values = {
        "deployment_profile": "demo",
        "local_only": False,
        "cloudflare_account_id": "account-123456",
        "cloudflare_api_token": "token-abcdef",
        "cloudflare_model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        "cloudflare_allowed_models": [
            "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        ],
        "cloudflare_timeout": 3.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class CloudflareSmokeScriptTest(unittest.TestCase):
    def test_missing_credentials_returns_error(self) -> None:
        with patch.object(
            cloudflare_smoke_test,
            "get_settings",
            return_value=_settings(cloudflare_account_id="", cloudflare_api_token=""),
        ):
            result = cloudflare_smoke_test.main([])

        self.assertEqual(result, 2)

    def test_success_path_verifies_token_and_inference(self) -> None:
        with (
            patch.object(cloudflare_smoke_test, "get_settings", return_value=_settings()),
            patch.object(
                cloudflare_smoke_test,
                "_verify_token",
                return_value=(200, {"success": True}),
            ) as verify,
            patch.object(
                cloudflare_smoke_test,
                "_post_ai_run",
                return_value=(
                    200,
                    {
                        "success": True,
                        "result": {
                            "response": '{"status":"ok","provider":"cloudflare"}'
                        },
                    },
                ),
            ) as run,
        ):
            result = cloudflare_smoke_test.main([])

        self.assertEqual(result, 0)
        verify.assert_called_once()
        run.assert_called_once()

    def test_skip_inference_only_verifies_token(self) -> None:
        with (
            patch.object(cloudflare_smoke_test, "get_settings", return_value=_settings()),
            patch.object(
                cloudflare_smoke_test,
                "_verify_token",
                return_value=(200, {"success": True}),
            ) as verify,
            patch.object(cloudflare_smoke_test, "_post_ai_run") as run,
        ):
            result = cloudflare_smoke_test.main(["--skip-inference"])

        self.assertEqual(result, 0)
        verify.assert_called_once()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
