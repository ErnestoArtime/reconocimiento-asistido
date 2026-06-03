from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.extraction_contract import SuggestionV1  # noqa: E402
from app.services.risk_flag_policy import apply_risk_flags  # noqa: E402


class RiskFlagPolicyTest(unittest.TestCase):
    def test_low_confidence_flag(self) -> None:
        [suggestion] = apply_risk_flags(
            [SuggestionV1(question_id="C5-1", confidence=0.4, evidence="x")],
            module="history",
            provider="heuristic",
            low_confidence_threshold=0.6,
        )

        self.assertIn("low_confidence", suggestion.risk_flags)

    def test_free_text_flag(self) -> None:
        [suggestion] = apply_risk_flags(
            [
                SuggestionV1(
                    question_id="A1",
                    selected_codes=["A1-T"],
                    free_text="texto libre",
                    confidence=0.8,
                    evidence="texto libre",
                )
            ],
            module="history",
            provider="heuristic",
        )

        self.assertIn("free_text", suggestion.risk_flags)

    def test_online_provider_flag(self) -> None:
        [suggestion] = apply_risk_flags(
            [SuggestionV1(question_id="C5-1", confidence=0.8, evidence="x")],
            module="history",
            provider="cloudflare",
        )

        self.assertIn("online_provider_used", suggestion.risk_flags)

    def test_uncertain_negation_flag(self) -> None:
        [suggestion] = apply_risk_flags(
            [
                SuggestionV1(
                    question_id="C5-121",
                    confidence=0.8,
                    evidence="no recuerda si fumo anteriormente",
                )
            ],
            module="history",
            provider="heuristic",
        )

        self.assertIn("uncertain_negation", suggestion.risk_flags)

    def test_historical_temporality_flag(self) -> None:
        [suggestion] = apply_risk_flags(
            [
                SuggestionV1(
                    question_id="C5-121",
                    confidence=0.8,
                    evidence="dejo de fumar hace tres anos",
                )
            ],
            module="history",
            provider="heuristic",
        )

        self.assertIn("historical_temporality", suggestion.risk_flags)

    def test_audio_timestamp_flag_is_opt_in(self) -> None:
        base = SuggestionV1(question_id="C5-1", confidence=0.8, evidence="x")

        [text_suggestion] = apply_risk_flags(
            [base],
            module="history",
            provider="heuristic",
            require_audio_timestamps=False,
        )
        [audio_suggestion] = apply_risk_flags(
            [base],
            module="history",
            provider="heuristic",
            require_audio_timestamps=True,
        )

        self.assertNotIn("no_audio_timestamp", text_suggestion.risk_flags)
        self.assertIn("no_audio_timestamp", audio_suggestion.risk_flags)

    def test_speaker_not_expected_flag(self) -> None:
        [suggestion] = apply_risk_flags(
            [
                SuggestionV1(
                    question_id="C5-1",
                    confidence=0.8,
                    evidence="x",
                    speaker="medico",
                )
            ],
            module="history",
            provider="heuristic",
        )

        self.assertIn("speaker_not_expected", suggestion.risk_flags)

    def test_existing_flags_are_not_duplicated(self) -> None:
        [suggestion] = apply_risk_flags(
            [
                SuggestionV1(
                    question_id="C5-1",
                    confidence=0.4,
                    evidence="x",
                    risk_flags=["low_confidence"],
                )
            ],
            module="history",
            provider="heuristic",
        )

        self.assertEqual(suggestion.risk_flags.count("low_confidence"), 1)


if __name__ == "__main__":
    unittest.main()
