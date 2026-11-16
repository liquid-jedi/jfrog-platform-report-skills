import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("audit", ROOT / "scripts" / "audit_weekly_coverage.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def archive(root: Path, server: str, key: str, start: str, end: str):
    run = root / server / "weekly" / key / "runs" / "r1"
    (run / "raw").mkdir(parents=True)
    evidence = {"provenance": {"prior_report_input_used": False}, "reporting": {"period": {"start": start, "end": end}}}
    (run / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    (run / "raw" / "manifest.json").write_text(json.dumps({"prior_report_input_used": False}), encoding="utf-8")
    pointer = root / server / "weekly" / key / "latest.json"
    pointer.write_text(json.dumps({"run_directory": str(run)}), encoding="utf-8")


class WeeklyCoverageAuditTests(unittest.TestCase):
    def test_previous_month_resolution(self):
        value = AUDIT.previous_month(datetime(2026, 11, 16, tzinfo=timezone.utc), "Asia/Kolkata")
        self.assertEqual(value, "2026-10")

    def test_complete_month_from_cross_boundary_weeks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for start, end in [
                ("2026-09-28T00:00:00Z", "2026-10-04T23:59:59Z"),
                ("2026-10-05T00:00:00Z", "2026-10-11T23:59:59Z"),
                ("2026-10-12T00:00:00Z", "2026-10-18T23:59:59Z"),
                ("2026-10-19T00:00:00Z", "2026-10-25T23:59:59Z"),
                ("2026-10-26T00:00:00Z", "2026-11-01T23:59:59Z"),
            ]:
                archive(root, "s", end[:10], start, end)
            result = AUDIT.audit(root, "s", "2026-10", "UTC", datetime(2026, 11, 2, tzinfo=timezone.utc))
            self.assertTrue(result["complete"])
            self.assertEqual(result["missing_weeks"], [])

    def test_missing_week_reports_backfill_eligibility(self):
        with tempfile.TemporaryDirectory() as temp:
            result = AUDIT.audit(Path(temp), "s", "2026-10", "UTC", datetime(2026, 11, 2, tzinfo=timezone.utc))
            self.assertFalse(result["complete"])
            self.assertTrue(result["suggest_backfill"])
            self.assertEqual(len(result["missing_weeks"]), 5)


if __name__ == "__main__":
    unittest.main()
