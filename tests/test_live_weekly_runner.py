import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_live_weekly.py"
SPEC = importlib.util.spec_from_file_location("run_live_weekly", RUNNER)
WEEKLY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WEEKLY)


class LiveWeeklyRunnerTests(unittest.TestCase):
    def test_parallel_collectors_preserve_declared_diagnostic_order(self):
        commands = [[sys.executable, name] for name in ("slow.py", "fast.py", "medium.py")]

        def fake_execute(command, required):
            delays = {"slow.py": 0.03, "fast.py": 0.0, "medium.py": 0.01}
            time.sleep(delays[Path(command[1]).name])
            return True, {"command": Path(command[1]).name, "required": required, "returncode": 0}

        diagnostics = []
        with patch.object(WEEKLY, "execute", side_effect=fake_execute):
            results = WEEKLY.run_parallel([(command, False) for command in commands], diagnostics)
        self.assertEqual(results, [True, True, True])
        self.assertEqual([row["command"] for row in diagnostics], ["slow.py", "fast.py", "medium.py"])

    def test_date_only_period_is_normalized_from_selected_timezone(self):
        start, end = WEEKLY.normalize_period("2026-11-09", "2026-11-15", "Asia/Kolkata")
        self.assertEqual(start, "2026-11-08T18:30:00Z")
        self.assertEqual(end, "2026-11-15T18:29:59Z")

    def test_naive_datetimes_are_interpreted_in_selected_timezone(self):
        start, end = WEEKLY.normalize_period(
            "2026-11-09T00:00:00", "2026-11-15T23:59:59", "Asia/Kolkata"
        )
        self.assertEqual(start, "2026-11-08T18:30:00Z")
        self.assertEqual(end, "2026-11-15T18:29:59Z")

    def test_skill_supports_short_natural_invocation(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        interface = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("generate weekly platform report", skill.lower())
        self.assertIn('default_prompt: "Generate weekly platform report"', interface)
        self.assertIn("jf config show", skill)

    def test_plan_always_collects_and_merges_ai_security(self):
        with tempfile.TemporaryDirectory() as temp:
            command = [sys.executable, str(RUNNER), "--server", "example", "--date-from", "2026-11-02T00:00:00Z",
                       "--date-to", "2026-11-08T23:59:59Z", "--period-key", "2026-11-08", "--month", "2026-11",
                       "--timezone", "UTC", "--report-root", temp, "--run-id", "r1", "--dry-run"]
            value = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
            commands = value["commands"]
            names = [Path(row[1]).name for row in commands]
            collector = commands[0]
            self.assertEqual(collector[collector.index("--timezone") + 1], "UTC")
            self.assertIn("collect_artifactory_traffic.py", names)
            self.assertIn("apply_traffic_evidence.py", names)
            self.assertIn("apply_economic_profile.py", names)
            economic = commands[names.index("apply_economic_profile.py")]
            self.assertIn("economic-profile.snapshot.json", " ".join(economic))
            self.assertIn("collect_skill_security.py", names)
            merge = commands[names.index("merge_current_evidence.py")]
            self.assertIn("--ai-catalog-evidence", merge)
            self.assertIn("ai-security.json", " ".join(merge))

    def test_dry_run_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as temp:
            subprocess.run([sys.executable, str(RUNNER), "--server", "example", "--date-from", "2026-11-02T00:00:00Z",
                            "--date-to", "2026-11-08T23:59:59Z", "--period-key", "2026-11-08", "--month", "2026-11",
                            "--report-root", temp, "--dry-run"], check=True, capture_output=True, text=True)
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_merge_preserves_distinct_ai_security_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); report = root / "report.json"; evidence = root / "ai.json"; output = root / "out.json"
            report.write_text(json.dumps({"ai_catalog": {"status": "partial", "metrics": []}}))
            evidence.write_text(json.dumps({"schema_version": "1.0", "collected_at": "2026-11-16T00:00:00Z",
                "source": "test", "status": "available", "inventory": {
                    "models": {"security_counts": {"malicious": 2}},
                    "mcp_servers": {"security_counts": {"malicious": 1, "suspicious": 3}},
                    "skills": {"security_counts": {"not_malicious": 4, "malicious": 1, "suspicious": 2, "not_scanned": 3}},
                    "plugins": {"security_counts": {"malicious": 1, "suspicious": 1}}}}))
            subprocess.run([sys.executable, str(ROOT / "scripts" / "merge_current_evidence.py"), "--report", str(report),
                            "--ai-catalog-evidence", str(evidence), "--output", str(output)], check=True, capture_output=True, text=True)
            metrics = {row["id"]: row["value"] for row in json.loads(output.read_text())["current_ai_security"]["metrics"]}
            self.assertEqual(metrics["ai-suspicious-skills"], 2)
            self.assertEqual(metrics["ai-malicious-mcp"], 1)
            self.assertEqual(metrics["ai-malicious-plugins"], 1)
            self.assertEqual(metrics["ai-malicious-models"], 2)


if __name__ == "__main__":
    unittest.main()
