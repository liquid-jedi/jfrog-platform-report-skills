import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ModularityAndPortabilityTests(unittest.TestCase):
    def test_section_catalog_is_machine_readable_and_complete(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "list_report_sections.py")], check=True, capture_output=True, text=True)
        value = json.loads(result.stdout)
        self.assertFalse(value["selection_required"])
        self.assertIn("ai-security", [row["id"] for row in value["sections"]])
        self.assertEqual(value["default"], "full")
        self.assertFalse(value["show_section_list"])

    def test_executive_is_a_profile_not_one_section(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "list_report_sections.py"), "--select", "executive"], check=True, capture_output=True, text=True)
        value = json.loads(result.stdout)
        self.assertEqual(value["profile"], "executive")
        self.assertIn("trend", value["selected"])
        self.assertIn("recommendations", value["selected"])

    def test_runner_passes_selected_modules_to_renderer(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_live_weekly.py"),
            "--server", "example", "--date-from", "2026-11-02T00:00:00Z", "--date-to", "2026-11-08T23:59:59Z",
            "--period-key", "2026-11-08", "--month", "2026-11", "--report-root", "/tmp/reports",
            "--modules", "executive,artifactory,evidence", "--dry-run"], check=True, capture_output=True, text=True)
        plan = json.loads(result.stdout)["commands"]
        render = next(row for row in plan if Path(row[1]).name == "render_report.py")
        self.assertEqual(render[render.index("--modules") + 1], "executive,artifactory,evidence")

    def test_template_is_versioned(self):
        template = (ROOT / "assets" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('data-jfrog-template-version="1.1.0"', template)
        self.assertIn('name="jfrog-report-template-version" content="1.1.0"', template)
        self.assertIn("position:sticky;top:0;z-index:30", template)
        self.assertIn("@page{size:A4", template)
        self.assertIn("thead{display:table-header-group}", template)

    def test_apm_manifest_is_target_agnostic(self):
        manifest = (ROOT / "apm.yml").read_text(encoding="utf-8")
        self.assertIn("name: jfrog-platform-report", manifest)
        self.assertIn("includes: auto", manifest)
        self.assertNotIn("targets:", manifest)


if __name__ == "__main__":
    unittest.main()
