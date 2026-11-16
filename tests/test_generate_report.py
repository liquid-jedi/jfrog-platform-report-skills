import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("generator", ROOT / "scripts" / "generate_report.py")
GEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GEN)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.evidence = json.loads((ROOT / "fixtures" / "artifactory-only.json").read_text())
        self.assumptions = json.loads((ROOT / "fixtures" / "assumptions.json").read_text())
        self.financial_assumptions = {
            "status": "customer_provided",
            "currency": "TST",
            "annual_cost": 100,
            "discount_rate": 0.08,
            "projections": [
                {"id": "automation-value", "label": "Automation value", "benefit_key": "automation", "category": "efficiency", "baseline_units": 100, "value_per_unit": 2, "adoption_coverage": 0.5, "realization_factor": 0.5, "conservative_factor": 0.7, "expected_factor": 1, "optimistic_factor": 1.3},
                {"id": "delivery-value", "label": "Delivery value", "benefit_key": "delivery", "category": "delivery", "baseline_units": 50, "value_per_unit": 4, "adoption_coverage": 0.5, "realization_factor": 0.5, "conservative_factor": 0.7, "expected_factor": 1, "optimistic_factor": 1.3}
            ]
        }

    def report(self, evidence=None, assumptions=None, profile="executive"):
        return GEN.calculate(evidence or self.evidence, assumptions or self.assumptions, profile)

    def test_artifactory_only(self):
        result = self.report()
        self.assertEqual(result["mode"], "offline-demo")
        self.assertTrue(any(m["id"] == "storage-tib" and m["classification"] == "derived" for m in result["metrics"]))

    def test_full_platform_fixture(self):
        evidence = json.loads((ROOT / "fixtures" / "full-platform.json").read_text())
        self.assertEqual(self.report(evidence=evidence)["mode"], "full-platform")

    def test_permission_failure_is_not_zero(self):
        evidence = copy.deepcopy(self.evidence)
        evidence["sources"][0].update(status="permission_denied", complete=False, reason="403")
        result = self.report(evidence=evidence)
        source = next(s for s in result["sources"] if s["id"] == "artifactory-repositories")
        self.assertEqual(source["status"], "permission_denied")
        self.assertFalse(source["complete"])

    def test_unlicensed_and_unused_are_distinct(self):
        evidence = json.loads((ROOT / "fixtures" / "full-platform.json").read_text())
        states = {s["id"]: s["status"] for s in self.report(evidence=evidence)["sources"]}
        self.assertEqual(states["runtime"], "no_data")
        self.assertEqual(states["agentic-remediation"], "unlicensed")

    def test_partial_source_preserved(self):
        evidence = copy.deepcopy(self.evidence)
        evidence["sources"][1].update(status="partial", complete=False, reason="pagination failure")
        source = self.report(evidence=evidence)["sources"][1]
        self.assertEqual(source["status"], "partial")

    def test_invalid_assumption(self):
        assumptions = copy.deepcopy(self.financial_assumptions)
        assumptions["projections"][0]["adoption_coverage"] = 1.2
        with self.assertRaisesRegex(ValueError, "factor over 1"):
            self.report(assumptions=assumptions)

    def test_currency_configuration(self):
        assumptions = copy.deepcopy(self.financial_assumptions)
        assumptions["currency"] = "INR"
        self.assertEqual(self.report(assumptions=assumptions)["financial"]["currency"], "INR")

    def test_scenarios_ordered(self):
        sensitivity = self.report(assumptions=self.financial_assumptions)["financial"]["sensitivity"]
        self.assertLess(float(sensitivity["conservative"]), float(sensitivity["expected"]))
        self.assertLess(float(sensitivity["expected"]), float(sensitivity["optimistic"]))

    def test_double_counting_rejected(self):
        assumptions = copy.deepcopy(self.financial_assumptions)
        assumptions["projections"][1]["benefit_key"] = assumptions["projections"][0]["benefit_key"]
        with self.assertRaisesRegex(ValueError, "double counting"):
            self.report(assumptions=assumptions)

    def test_zero_cost_roi_unavailable_and_payback_zero(self):
        assumptions = copy.deepcopy(self.financial_assumptions)
        assumptions["annual_cost"] = 0
        financial = self.report(assumptions=assumptions)["financial"]
        self.assertIsNone(financial["roi_percent"])
        self.assertEqual(financial["payback_years"], "0.00")

    def test_zero_benefit_payback_unavailable(self):
        assumptions = copy.deepcopy(self.financial_assumptions)
        assumptions["projections"] = []
        self.assertIsNone(self.report(assumptions=assumptions)["financial"]["payback_years"])

    def test_profiles_are_modular(self):
        self.assertNotEqual(self.report(profile="adoption")["modules"], self.report(profile="full")["modules"])

    def test_product_profiles_are_independently_selectable(self):
        for profile in ("curation", "xray", "artifactory", "ai-security", "jas"):
            self.assertEqual(self.report(profile=profile)["modules"], [profile])

    def test_default_financials_are_unavailable(self):
        financial = self.report()["financial"]
        self.assertFalse(financial["available"])
        self.assertIsNone(financial["currency"])
        self.assertIsNone(financial["annual_benefit"])

    def test_period_comparison_and_ytd_are_explicit(self):
        result = self.report()
        self.assertEqual(result["period_activity"]["downloads_delta_pct"], "8.2")
        self.assertEqual(result["year_to_date"]["downloads"], 149000000)
        self.assertEqual(len(result["reporting"]["history"]), 3)

    def test_html_generation(self):
        report = self.report()
        html = GEN.render(report, ROOT / "assets" / "dashboard.html")
        self.assertIn("JFrog Platform Value &amp; Risk Report", html)
        self.assertIn("data:font/ttf;base64,", html)
        self.assertNotIn("__JFROG_OPEN_SANS_FONT__", html)
        self.assertNotIn("__JFROG_PLATFORM_REPORT_DATA__", html)
        self.assertIn('type="application/json"', html)
        self.assertIn('data-export-mode="executive"', html)
        self.assertIn('data-export-mode="custom"', html)
        self.assertIn('id="print-report"', html)
        self.assertIn('"classification":"unavailable"', html)
        self.assertIsNone(report["financial"]["currency"])

    def test_every_metric_has_plain_language_explanation(self):
        for item in self.report(profile="full")["metrics"]:
            self.assertTrue(item["meaning"], item["id"])
            self.assertTrue(item["why_it_matters"], item["id"])

    def test_cli_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            report = self.report()
            (out / "data.json").write_text(json.dumps(report))
            (out / "report.html").write_text(GEN.render(report, ROOT / "assets" / "dashboard.html"))
            self.assertGreater((out / "report.html").stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
