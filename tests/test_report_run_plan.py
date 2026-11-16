import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("plan", ROOT / "scripts" / "plan_report_run.py")
PLAN = importlib.util.module_from_spec(SPEC)
import sys
sys.path.insert(0, str(ROOT / "scripts"))
SPEC.loader.exec_module(PLAN)


class ReportRunPlanTests(unittest.TestCase):
    def test_default_archive_is_last_completed_week(self):
        value = PLAN.plan("example", Path("/reports"), "completed-week", "Asia/Kolkata",
                          datetime(2026, 11, 16, 10, tzinfo=timezone.utc))
        self.assertEqual(value["period"]["period_key"], "2026-11-15")
        self.assertEqual(value["archive"]["period_directory"], "/reports/example/weekly/2026-11-15")

    def test_reruns_get_distinct_run_directories(self):
        first = PLAN.plan("example", Path("/reports"), "completed-week", "UTC",
                          datetime(2026, 11, 16, 1, tzinfo=timezone.utc))
        second = PLAN.plan("example", Path("/reports"), "completed-week", "UTC",
                           datetime(2026, 11, 16, 2, tzinfo=timezone.utc))
        self.assertEqual(first["archive"]["period_directory"], second["archive"]["period_directory"])
        self.assertNotEqual(first["archive"]["run_directory"], second["archive"]["run_directory"])


if __name__ == "__main__":
    unittest.main()
