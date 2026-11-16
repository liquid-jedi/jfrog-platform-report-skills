import importlib.util
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("period", ROOT / "scripts" / "resolve_reporting_period.py")
PERIOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PERIOD)


class ReportingPeriodTests(unittest.TestCase):
    def test_completed_week_is_stable_on_every_run_day(self):
        expected = None
        for day in range(9, 16):
            result = PERIOD.resolve("completed-week", "Asia/Kolkata", datetime(2026, 11, day, 12, tzinfo=timezone.utc))
            bounds = (result["local"]["start"], result["local"]["end"])
            expected = expected or bounds
            self.assertEqual(bounds, expected)
        self.assertEqual(expected, ("2026-11-02T00:00:00+05:30", "2026-11-08T23:59:59+05:30"))

    def test_current_week_is_explicitly_partial(self):
        result = PERIOD.resolve("current-week", "Asia/Kolkata", datetime(2026, 11, 16, 10, tzinfo=timezone.utc))
        self.assertEqual(result["completeness"], "week_to_date")
        self.assertEqual(result["local"]["start"], "2026-11-16T00:00:00+05:30")

    def test_dst_week_uses_timezone_boundaries(self):
        result = PERIOD.resolve("completed-week", "America/New_York", datetime(2026, 11, 4, 12, tzinfo=timezone.utc))
        self.assertEqual(result["local"]["start"], "2026-10-26T00:00:00-04:00")
        self.assertEqual(result["local"]["end"], "2026-11-01T23:59:59-05:00")

    def test_explicit_dates_are_inclusive(self):
        result = PERIOD.resolve("explicit", "UTC", datetime(2026, 11, 16, tzinfo=timezone.utc), "2026-11-03", "2026-11-09")
        self.assertEqual(result["utc"], {"start": "2026-11-03T00:00:00Z", "end": "2026-11-09T23:59:59Z"})

    def test_week_ending_resolves_seven_inclusive_local_dates(self):
        result = PERIOD.resolve("week-ending", "Asia/Kolkata", datetime(2026, 11, 16, tzinfo=timezone.utc), date_to="2026-11-15")
        self.assertEqual(result["local"]["start"], "2026-11-09T00:00:00+05:30")
        self.assertEqual(result["local"]["end"], "2026-11-15T23:59:59+05:30")

    def test_completed_calendar_month(self):
        result = PERIOD.resolve("calendar-month", "UTC", datetime(2026, 11, 16, tzinfo=timezone.utc), month="2026-10")
        self.assertEqual(result["completeness"], "complete")
        self.assertEqual(result["utc"], {"start": "2026-10-01T00:00:00Z", "end": "2026-10-31T23:59:59Z"})

    def test_timezone_prefers_report_environment(self):
        self.assertEqual(PERIOD.detect_timezone({"JFROG_REPORT_TIMEZONE": "Asia/Kolkata"}), "Asia/Kolkata")

    def test_timezone_detects_iana_localtime_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); zone = root / "zoneinfo" / "Asia" / "Kolkata"; zone.parent.mkdir(parents=True)
            zone.write_text(""); link = root / "localtime"; link.symlink_to(zone)
            self.assertEqual(PERIOD.detect_timezone({}, link, root / "missing"), "Asia/Kolkata")


if __name__ == "__main__":
    unittest.main()
