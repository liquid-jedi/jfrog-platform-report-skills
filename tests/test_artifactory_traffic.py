import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("traffic", ROOT / "scripts" / "collect_artifactory_traffic.py")
TRAFFIC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRAFFIC)


class TrafficTests(unittest.TestCase):
    def test_successful_gets_and_writes_are_counted(self):
        text = '\n'.join([
            'http_time_resolve_self_seconds_count{group="download",method="GET",package="npm",status="200"} 10',
            'http_time_resolve_self_seconds_count{group="download",method="HEAD",package="npm",status="200"} 99',
            'http_time_resolve_self_seconds_count{group="download",method="GET",package="npm",status="404"} 8',
            'http_time_resolve_self_seconds_count{group="upload",method="PUT",package="npm",status="201"} 3',
        ])
        result = TRAFFIC.aggregate(text)
        self.assertEqual(result["download_requests_total"], 10)
        self.assertEqual(result["upload_requests_total"], 3)

    def test_delta_requires_two_monotonic_snapshots(self):
        current = {"download_requests_total": 15, "upload_requests_total": 5,
                   "cache_fs_download_total": None, "cache_fs_not_found_total": None}
        prior = {"counters": {"download_requests_total": 10, "upload_requests_total": 2}}
        result = TRAFFIC.delta(current, prior)
        self.assertEqual(result["download_requests_delta"], 5)
        self.assertEqual(result["upload_requests_delta"], 3)
        self.assertIsNone(result["cache_fs_hit_rate"])


if __name__ == "__main__":
    unittest.main()
