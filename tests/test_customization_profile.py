import importlib.util
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "customization_profile.py"
SPEC = importlib.util.spec_from_file_location("customization_profile", MODULE_PATH)
PROFILE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROFILE)


class CustomizationProfileTests(unittest.TestCase):
    def write_profile(self, root: Path, content: str) -> Path:
        path = root / "profile.toml"
        path.write_text(textwrap.dedent(content), encoding="utf-8")
        return path

    def test_absent_profile_preserves_existing_defaults(self):
        value = PROFILE.load_profile(None)
        self.assertEqual(value["name"], "default")
        self.assertEqual(value["collectors"]["base-platform"], "required")
        self.assertEqual(value["collectors"]["access"], "auto")
        self.assertEqual(value["scope"]["type"], "all")
        self.assertIn("executive", value["sections"])
        self.assertIn("economic", value["sections"])

    def test_profile_controls_optional_collectors_and_sections(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_profile(Path(temp), """
                profile_version = 1
                name = "focused"
                [collectors]
                access = "disabled"
                apptrust = "required"
                [sections]
                include = ["executive", "apptrust", "evidence"]
            """)
            value = PROFILE.load_profile(path)
            self.assertEqual(value["collectors"]["access"], "disabled")
            self.assertEqual(value["collectors"]["apptrust"], "required")
            self.assertEqual(value["sections"], ["executive", "apptrust", "evidence"])
            self.assertEqual(value["warnings"], [])

    def test_core_collector_cannot_be_disabled_in_version_one(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_profile(Path(temp), """
                profile_version = 1
                [collectors]
                base-platform = "disabled"
            """)
            with self.assertRaisesRegex(ValueError, "not configurable"):
                PROFILE.load_profile(path)

    def test_source_repository_scope_requires_explicit_mapping(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_profile(Path(temp), """
                profile_version = 1
                [scope]
                type = "source_repository"
                include = ["acme/api"]
            """)
            with self.assertRaisesRegex(ValueError, "explicit source_mappings"):
                PROFILE.load_profile(path)

    def test_source_mapping_selects_only_explicit_jfrog_repositories(self):
        profile = PROFILE.default_profile()
        profile["scope"] = {
            "type": "source_repository", "include": ["acme/payments-*"], "exclude": [],
            "mapping_policy": "explicit_only", "source_mappings": [
                {"source": "acme/payments-api", "repositories": ["pay-local"], "projects": ["PAY"]}
            ],
        }
        repositories = [
            {"key": "pay-local", "projectKey": "PAY"},
            {"key": "pay-remote", "projectKey": "PAY"},
            {"key": "other", "projectKey": "OTHER"},
        ]
        selected, ledger = PROFILE.resolve_repository_scope(profile, repositories)
        self.assertEqual(selected, {"pay-local", "pay-remote"})
        self.assertEqual(ledger["mapped_sources"], ["acme/payments-api"])
        self.assertEqual(ledger["selected_repositories"], 2)

    def test_auto_collectors_without_scope_support_are_disabled(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_profile(Path(temp), """
                profile_version = 1
                [sections]
                include = ["executive", "access", "evidence"]
                [scope]
                type = "artifactory_repository"
                include = ["repo-a"]
            """)
            value = PROFILE.load_profile(path)
            self.assertEqual(value["collectors"]["access"], "disabled")
            self.assertEqual(value["collector_decisions"]["access"]["reason"], "scope_not_supported")
            self.assertIn("section access is selected", value["warnings"][0])

    def test_required_collector_without_scope_support_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_profile(Path(temp), """
                profile_version = 1
                [collectors]
                access = "required"
                [scope]
                type = "artifactory_repository"
                include = ["repo-a"]
            """)
            with self.assertRaisesRegex(ValueError, "does not support artifactory_repository"):
                PROFILE.load_profile(path)

    def test_runner_uses_profile_sections_without_changing_legacy_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = self.write_profile(root, """
                profile_version = 1
                [sections]
                include = ["executive", "evidence"]
            """)
            command = [sys.executable, str(ROOT / "scripts" / "run_live_weekly.py"),
                       "--server", "example", "--date-from", "2026-11-02", "--date-to", "2026-11-08",
                       "--period-key", "2026-11-08", "--month", "2026-11", "--report-root", str(root / "reports"),
                       "--profile", str(profile), "--dry-run"]
            plan = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
            render = next(row for row in plan["commands"] if Path(row[1]).name == "render_report.py")
            self.assertEqual(render[render.index("--modules") + 1], "executive,evidence")
            self.assertFalse((root / "reports").exists())

    def test_repository_scope_is_applied_before_metric_calculation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); raw = root / "raw"; raw.mkdir()
            profile = self.write_profile(root, """
                profile_version = 1
                [scope]
                type = "artifactory_repository"
                include = ["repo-a"]
            """)
            evidence = {
                "provenance": {"server_id": "example"},
                "reporting": {"cadence": "weekly", "timezone": "UTC", "period": {
                    "start": "2026-11-02T00:00:00Z", "end": "2026-11-08T23:59:59Z"}},
                "artifactory": {"as_of": "2026-11-09T00:00:00Z"},
                "ai_catalog": {"as_of": "2026-11-09T00:00:00Z"},
                "curation": {"status": "available", "period": {"collection": {
                    "coverage": "complete", "available_start": "2026-11-02T00:00:00Z",
                    "available_end": "2026-11-08T23:59:59Z", "reason": None}}},
                "xray": {"period": {"collection": {"total_reported": 2}}},
            }
            (root / "evidence.json").write_text(json.dumps(evidence))
            (raw / "artifactory-repositories.json").write_text(json.dumps([
                {"key": "repo-a", "type": "LOCAL", "packageType": "Maven", "projectKey": "A"},
                {"key": "repo-b", "type": "LOCAL", "packageType": "Npm", "projectKey": "B"},
            ]))
            (raw / "artifactory-storage.json").write_text(json.dumps({
                "binariesSummary": {"artifactsSize": "30 GB", "artifactsCount": 30, "optimization": "1.2"},
                "repositoriesSummaryList": [
                    {"repoKey": "repo-a", "usedSpaceInBytes": 10, "usedSpace": "10 B", "filesCount": 1, "packageType": "Maven"},
                    {"repoKey": "repo-b", "usedSpaceInBytes": 20, "usedSpace": "20 B", "filesCount": 2, "packageType": "Npm"},
                ],
            }))
            (raw / "xray-watches.json").write_text("[]")
            (raw / "xray-policies.json").write_text("[]")
            (raw / "xray-indexed-repositories.json").write_text(json.dumps({
                "indexed_repos": [{"name": "repo-a", "pkg_type": "Maven"}, {"name": "repo-b", "pkg_type": "Npm"}],
                "non_indexed_repos": [],
            }))
            (raw / "curation-audit-w01-00000000.json").write_text(json.dumps({"data": [
                {"curated_repository_name": "repo-a", "action": "allowed", "username": "a"},
                {"curated_repository_name": "repo-b", "action": "blocked", "username": "b"},
            ]}))
            (raw / "xray-violations-000001.json").write_text(json.dumps({"violations": [
                {"severity": "High", "impacted_artifacts": ["repo-a/path/a"]},
                {"severity": "Critical", "impacted_artifacts": ["repo-b/path/b"]},
            ]}))
            output = root / "report.json"
            subprocess.run([sys.executable, str(ROOT / "scripts" / "build_report_from_live_evidence.py"),
                            "--evidence", str(root / "evidence.json"), "--raw-dir", str(raw),
                            "--profile", str(profile), "--output", str(output)],
                           check=True, capture_output=True, text=True)
            report = json.loads(output.read_text())
            platform = {row["id"]: row["value"] for row in report["platform"]["metrics"]}
            curation = {row["id"]: row["value"] for row in report["curation"]["metrics"]}
            xray = {row["id"]: row["value"] for row in report["xray"]["metrics"]}
            self.assertEqual(platform["repositories"], 1)
            self.assertEqual(curation["curation-decisions"], 1)
            self.assertEqual(xray["xray-new-findings"], 1)
            self.assertEqual(report["scope_ledger"]["selected_repository_keys"], ["repo-a"])


if __name__ == "__main__":
    unittest.main()
