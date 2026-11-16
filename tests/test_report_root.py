import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("report_root", ROOT / "scripts" / "resolve_report_root.py")
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


class ReportRootTests(unittest.TestCase):
    def test_first_run_requires_input_and_offers_default(self):
        with tempfile.TemporaryDirectory() as temp:
            value = MODULE.resolve("example", None, Path(temp) / "missing.json", {})
        self.assertEqual(value["status"], "needs_input")
        self.assertTrue(value["suggested_report_root"].endswith("jfrog-platform-reports"))
        self.assertEqual(value["path_template"], "<report-root>/<instance>/weekly/<week-ending>/report.html")

    def test_environment_root_is_instance_scoped(self):
        with tempfile.TemporaryDirectory() as temp:
            value = MODULE.resolve("instance-a", None, Path(temp) / "missing.json", {"JFROG_REPORT_ROOT": temp})
        self.assertEqual(value["status"], "resolved")
        self.assertEqual(Path(value["instance_root"]), Path(temp).resolve() / "instance-a")

    def test_per_instance_saved_root_wins_over_global(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "config.json"
            config.write_text(json.dumps({"report_root": "/global", "instances": {"b": {"report_root": "/instance-b"}}}))
            value = MODULE.resolve("b", None, config, {})
        self.assertEqual(value["report_root"], "/instance-b")


if __name__ == "__main__":
    unittest.main()
