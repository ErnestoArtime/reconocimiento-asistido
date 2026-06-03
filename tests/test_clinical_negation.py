from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.clinical_negation import (  # noqa: E402
    detect_clinical_negation,
    has_category,
    load_negation_rules,
)


class ClinicalNegationTest(unittest.TestCase):
    def test_rules_file_loads(self) -> None:
        rules = load_negation_rules()
        self.assertIn("negation_pre", rules)
        self.assertIn("uncertainty", rules)
        self.assertIn("historical", rules)

    def test_no_fuma_is_present_negation(self) -> None:
        findings = detect_clinical_negation("El paciente no fuma actualmente.")
        self.assertTrue(has_category(findings, "negation_pre"))
        self.assertIn("present", {finding.temporality for finding in findings})

    def test_nunca_ha_fumado_is_negation(self) -> None:
        findings = detect_clinical_negation("Nunca ha fumado.")
        self.assertTrue(has_category(findings, "negation_pre"))

    def test_dejo_de_fumar_is_historical(self) -> None:
        findings = detect_clinical_negation("Dejo de fumar hace tres anos.")
        self.assertTrue(has_category(findings, "historical"))
        self.assertIn("historical", {finding.temporality for finding in findings})

    def test_no_recuerda_is_uncertainty(self) -> None:
        findings = detect_clinical_negation("No recuerda si fumo anteriormente.")
        self.assertTrue(has_category(findings, "uncertainty"))

    def test_niega_alcohol_is_negation(self) -> None:
        findings = detect_clinical_negation("Niega alcohol.")
        self.assertTrue(has_category(findings, "negation_pre"))

    def test_sin_alergias_conocidas_is_negation(self) -> None:
        findings = detect_clinical_negation("Sin alergias conocidas.")
        self.assertTrue(has_category(findings, "negation_pre"))

    def test_pseudo_negation_does_not_emit_inner_negation(self) -> None:
        findings = detect_clinical_negation("No niega consumo de alcohol.")
        categories = [finding.category for finding in findings]
        self.assertIn("pseudo_negation", categories)
        self.assertNotIn("negation_pre", categories)


if __name__ == "__main__":
    unittest.main()
