import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("economic_profile", ROOT / "scripts" / "economic_profile.py")
ECON = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ECON)
BENCHMARK = json.loads((ROOT / "benchmarks" / "forrester-tei-2026.json").read_text())


def approved(currency="USD", benchmark=True):
    row = {"id": "vulnerability-prevention", "label": "Reduced vulnerabilities", "enabled": True,
           "benefit_key": "vulnerability-prevention", "category": "risk_reduction", "baseline_units": 100,
           "baseline_source": "customer-approved baseline", "adoption_coverage": 0.5,
           "realization_factor": 0.5, "conservative_factor": 0.8, "expected_factor": 1,
           "optimistic_factor": 1.2, "confidence": "medium"}
    row["benchmark_unit" if benchmark else "value_per_unit"] = "reduced_vulnerabilities" if benchmark else 100
    return {"schema_version": "1.0", "server_id": "example", "profile_id": "example-economics",
            "status": "customer_approved", "mode": "tei_assisted" if benchmark else "customer",
            "currency": currency, "discount_rate": 0.1,
            "costs": {"implementation_one_time": 100, "annual_jfrog_license": 500,
                      "annual_professional_services": 250, "annual_internal_platform_labor": 150},
            "benefit_models": [row], "approved_by": "Finance", "approved_at": "2026-11-17T00:00:00Z"}


class EconomicProfileTests(unittest.TestCase):
    def test_no_profile_is_benchmark_not_customer_projection(self):
        with tempfile.TemporaryDirectory() as temp:
            model, profile, _ = ECON.build("example", BENCHMARK, Path(temp) / "missing.json")
        self.assertIsNone(profile); self.assertEqual(model["classification"], "benchmark")
        self.assertEqual(model["summary"]["roi_percent"], 282); self.assertFalse(model["profile"]["applied"])

    def test_draft_profile_is_not_applied(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profile.json"; value = approved(); value["status"] = "draft"
            path.write_text(json.dumps(value)); model, _, _ = ECON.build("example", BENCHMARK, path)
        self.assertEqual(model["status"], "benchmark"); self.assertEqual(model["profile"]["status"], "draft")

    def test_approved_tei_profile_calculates_deterministically(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profile.json"; path.write_text(json.dumps(approved()))
            model, _, _ = ECON.build("example", BENCHMARK, path)
        self.assertEqual(model["status"], "projected"); self.assertEqual(model["scenarios"]["expected"], "9787.50")
        self.assertEqual(model["summary"]["annual_cost"], "900.00"); self.assertEqual(model["confidence"], "medium")

    def test_duplicate_benefits_are_rejected(self):
        profile = approved(); profile["benefit_models"].append(dict(profile["benefit_models"][0], id="duplicate"))
        with self.assertRaisesRegex(ValueError, "duplicate"): ECON.validate_approved(profile)

    def test_non_usd_benchmark_requires_explicit_fx(self):
        with self.assertRaisesRegex(ValueError, "conversion"): ECON.validate_approved(approved("INR"))

    def test_profile_path_is_per_instance_and_xdg_portable(self):
        path = ECON.default_profile_path("customer/site", {"XDG_CONFIG_HOME": "/tmp/config"})
        self.assertEqual(path, Path("/tmp/config/jfrog-platform-value-report/instances/customer-site/economic-profile.json"))


if __name__ == "__main__": unittest.main()
