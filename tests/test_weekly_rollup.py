import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rollup", ROOT / "scripts" / "rollup_weekly_archives.py")
ROLLUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ROLLUP)


def write_run(root: Path, name: str, start: str, end: str, events: list[dict]) -> Path:
    run = root / name
    raw = run / "raw"
    raw.mkdir(parents=True)
    payload = json.dumps({"data": events}, sort_keys=True, separators=(",", ":")) + "\n"
    path = raw / "curation-audit-w01-00000000.json"
    path.write_text(payload, encoding="utf-8")
    source = {"raw_file": path.name, "sha256": hashlib.sha256(payload.encode()).hexdigest()}
    (raw / "manifest.json").write_text(json.dumps({"sources": [source]}), encoding="utf-8")
    evidence = {
        "provenance": {"prior_report_input_used": False, "collection_started_at": end},
        "reporting": {"period": {"start": start, "end": end}},
        "artifactory": {"repositories_total": 10}, "xray": {"inventory": {"watches_total": 2}},
    }
    (run / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    return run


class WeeklyRollupTests(unittest.TestCase):
    def test_cross_boundary_events_are_filtered_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            events = [
                {"id": "before", "created_at": "2026-09-30T12:00:00Z", "action": "approved"},
                {"id": "inside", "created_at": "2026-10-01T12:00:00Z", "action": "blocked", "username": "a", "package_name": "p", "package_version": "1"},
            ]
            archives = [write_run(root, "w1", "2026-09-28T00:00:00Z", "2026-10-31T23:59:59Z", events)]
            result = ROLLUP.rollup("2026-10", "UTC", archives)
            self.assertTrue(result["coverage"]["complete"])
            self.assertEqual(result["curation"]["events"], 1)
            self.assertEqual(result["curation"]["unique_users"], 1)

    def test_missing_week_makes_month_unavailable_not_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = write_run(root, "w1", "2026-10-01T00:00:00Z", "2026-10-07T23:59:59Z", [])
            result = ROLLUP.rollup("2026-10", "UTC", [archive])
            self.assertFalse(result["coverage"]["complete"])
            self.assertIsNone(result["curation"]["events"])
            self.assertTrue(result["coverage"]["gaps"])

    def test_checksum_failure_rejects_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = write_run(root, "w1", "2026-10-01T00:00:00Z", "2026-10-31T23:59:59Z", [])
            (archive / "raw" / "curation-audit-w01-00000000.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                ROLLUP.rollup("2026-10", "UTC", [archive])


if __name__ == "__main__":
    unittest.main()
