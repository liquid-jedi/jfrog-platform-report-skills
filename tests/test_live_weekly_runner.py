import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_live_weekly.py"


class LiveWeeklyRunnerTests(unittest.TestCase):
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
