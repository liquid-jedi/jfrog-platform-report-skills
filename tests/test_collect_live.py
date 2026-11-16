import importlib.util
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("collect_live", ROOT / "scripts" / "collect_live.py")
LIVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LIVE)


class FakeCollector:
    def __init__(self):
        self.paths = []

    def api(self, source_id, path, **kwargs):
        self.paths.append(path)
        return {"meta": {"total_count": 0}, "data": []}


class ViolationCollector:
    def __init__(self):
        self.offsets = []

    def api(self, source_id, path, **kwargs):
        offset = kwargs["body"]["pagination"]["offset"]
        self.offsets.append(offset)
        total = 1200
        count = min(500, total - offset)
        return {"total_violations": total, "violations": [
            {"id": value} for value in range(offset, offset + count)
        ]}


class CollectLiveTests(unittest.TestCase):
    def test_connection_reset_is_retried_once(self):
        reset = subprocess.CompletedProcess([], 1, "", "connection reset by peer")
        success = subprocess.CompletedProcess([], 0, json.dumps({"ok": True}), "")
        with tempfile.TemporaryDirectory() as temp, patch.object(
            LIVE.subprocess, "run", side_effect=[reset, success]
        ) as mocked:
            payload = LIVE.Collector("example", Path(temp)).api("source", "/artifactory/api/test")
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(mocked.call_count, 2)

    def test_xray_pagination_uses_record_offsets(self):
        collector = ViolationCollector()
        rows, meta = LIVE.fetch_violations(
            collector, "2026-11-08T18:30:00Z", "2026-11-15T18:29:59Z"
        )
        self.assertEqual(sorted(collector.offsets), [0, 500, 1000])
        self.assertEqual(len(rows), 1200)
        self.assertTrue(meta["complete"])

    def test_curation_preserves_rfc3339_timestamp_separators(self):
        collector = FakeCollector()
        rows, meta = LIVE.fetch_curation(
            collector, "2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z",
            datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc),
        )
        self.assertEqual(rows, [])
        self.assertTrue(meta["complete"])
        self.assertIn("created_at_start=2026-09-01T00:00:00Z", collector.paths[0])
        self.assertNotIn("%3A", collector.paths[0])

    def test_month_is_split_into_non_overlapping_supported_windows(self):
        collector = FakeCollector()
        rows, meta = LIVE.fetch_curation(
            collector, "2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z",
            datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc),
        )
        self.assertEqual(rows, [])
        self.assertEqual(meta["windows"], 5)
        self.assertEqual(len(collector.paths), 5)
        self.assertIn("created_at_end=2026-09-07T23:59:59Z", collector.paths[0])
        self.assertIn("created_at_start=2026-09-08T00:00:00Z", collector.paths[1])
        self.assertIn("created_at_end=2026-09-30T23:59:59Z", collector.paths[-1])

    def test_expired_curation_period_is_unavailable_not_zero(self):
        collector = FakeCollector()
        rows, meta = LIVE.fetch_curation(
            collector, "2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z",
            datetime(2026, 11, 16, tzinfo=timezone.utc),
        )
        self.assertEqual(rows, [])
        self.assertEqual(meta["coverage"], "unavailable")
        self.assertFalse(meta["complete"])
        self.assertEqual(collector.paths, [])

    def test_partially_retained_month_is_not_a_month_total(self):
        collector = FakeCollector()
        rows, meta = LIVE.fetch_curation(
            collector, "2026-10-01T00:00:00Z", "2026-10-31T23:59:59Z",
            datetime(2026, 11, 16, tzinfo=timezone.utc),
        )
        self.assertEqual(rows, [])
        self.assertEqual(meta["coverage"], "partial")
        self.assertFalse(meta["complete"])
        self.assertIn("created_at_start=2026-10-17T00:00:00Z", collector.paths[0])

    def test_collector_has_no_prior_report_or_snapshot_argument(self):
        source = (ROOT / "scripts" / "collect_live.py").read_text(encoding="utf-8")
        self.assertNotIn("resume-ciso-raw", source)
        self.assertNotIn("previous_snapshot", source)


if __name__ == "__main__":
    unittest.main()
