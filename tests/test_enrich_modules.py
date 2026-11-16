import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("enrich", ROOT / "scripts" / "enrich_report_modules.py")
ENRICH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENRICH)


class EnrichmentTests(unittest.TestCase):
    def test_cross_watch_occurrences_are_not_double_counted(self):
        common = {
            "issue_id": "XRAY-1",
            "infected_components": ["npm://a:1"],
            "impacted_artifacts": ["default/npm-local/a.tgz"],
        }
        rows = [dict(common, watch_name="watch-a", violation_id="1"),
                dict(common, watch_name="watch-b", violation_id="2")]
        self.assertEqual(len(ENRICH.deduplicate_violations(rows)), 1)

    def test_distinct_impacted_artifacts_are_preserved(self):
        rows = [
            {"issue_id": "XRAY-1", "infected_components": ["npm://a:1"], "impacted_artifacts": ["default/repo/a.tgz"]},
            {"issue_id": "XRAY-1", "infected_components": ["npm://a:1"], "impacted_artifacts": ["default/repo/b.tgz"]},
        ]
        self.assertEqual(len(ENRICH.deduplicate_violations(rows)), 2)


if __name__ == "__main__":
    unittest.main()
