import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("skill_security", ROOT / "scripts" / "collect_skill_security.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
NORMALIZE_SPEC = importlib.util.spec_from_file_location(
    "ai_security_evidence", ROOT / "scripts" / "build_ai_security_evidence.py")
NORMALIZE = importlib.util.module_from_spec(NORMALIZE_SPEC)
NORMALIZE_SPEC.loader.exec_module(NORMALIZE)


class SkillSecurityTests(unittest.TestCase):
    def test_statuses_are_normalized_without_changing_meaning(self):
        self.assertEqual(MODULE.display_status("APPROVED"), "Not malicious")
        self.assertEqual(MODULE.display_status("unscanned"), "Not scanned")
        self.assertEqual(MODULE.display_status("MALICIOUS"), "Malicious")
        self.assertEqual(MODULE.display_status("IN_PROGRESS"), "Scanning")
        self.assertEqual(MODULE.display_status("SCAN_IN_PROGRESS"), "Scanning")
        self.assertEqual(MODULE.display_status("XRAY_DISABLED_FOR_REPO"), "Not scanned")

    def test_versions_sort_numerically(self):
        self.assertGreater(MODULE.version_key("1.10.0"), MODULE.version_key("1.9.9"))

    def test_default_repository_scope_is_not_a_named_project(self):
        self.assertEqual(MODULE.classify_project_assignment("default", {"app1"}), ("Unlinked", []))
        self.assertEqual(MODULE.classify_project_assignment("app1", {"app1"}), ("Linked", ["app1"]))
        self.assertEqual(MODULE.classify_project_assignment("hidden", {"app1"}), ("Unknown", []))

    def test_ai_asset_statuses_are_not_merged(self):
        assets = [
            {"security_status": "Malicious"},
            {"security_status": "Suspicious"},
            {"security_status": "Not malicious"},
            {"security_status": "N/A"},
        ]
        self.assertEqual(NORMALIZE.counts(assets), {
            "malicious": 1, "suspicious": 1, "not_malicious": 1,
            "scanning": 0, "not_scanned": 0, "n_a": 1,
        })

    def test_missing_plugin_scan_is_na(self):
        self.assertEqual(NORMALIZE.label(None), "N/A")


if __name__ == "__main__":
    unittest.main()
