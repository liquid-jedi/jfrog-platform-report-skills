import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("collect_apptrust", ROOT / "scripts" / "collect_apptrust.py")
APPTRUST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APPTRUST)


class FakeClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.documents = []

    def query(self, source_id, document):
        self.documents.append((source_id, document))
        if not self.payloads:
            raise AssertionError("unexpected query")
        return self.payloads.pop(0)


def inventory_payload(total, rows, has_next=False, cursor=None):
    return {"data": {"applications": {"searchApplications": {
        "totalCount": total,
        "edges": [{"node": row} for row in rows],
        "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
    }}}}


class AppTrustCollectorTests(unittest.TestCase):
    def test_inventory_follows_cursor_until_reported_total_is_reconciled(self):
        client = FakeClient([
            inventory_payload(3, [{"key": "a"}, {"key": "b"}], True, "cursor-2"),
            inventory_payload(3, [{"key": "c"}], False, "cursor-3"),
        ])
        rows, pages = APPTRUST.collect_inventory(client)
        self.assertEqual([row["key"] for row in rows], ["a", "b", "c"])
        self.assertEqual(pages, 2)
        self.assertIn('after: "cursor-2"', client.documents[1][1])

    def test_inventory_rejects_cursor_stall(self):
        client = FakeClient([inventory_payload(2, [{"key": "a"}], True, None)])
        with self.assertRaisesRegex(RuntimeError, "did not advance"):
            APPTRUST.collect_inventory(client)

    def test_inventory_rejects_duplicate_application_keys(self):
        client = FakeClient([inventory_payload(2, [{"key": "a"}, {"key": "a"}])])
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            APPTRUST.collect_inventory(client)

    def test_inventory_rejects_incomplete_total(self):
        client = FakeClient([inventory_payload(2, [{"key": "a"}])])
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            APPTRUST.collect_inventory(client)

    def test_nested_detail_pagination_is_never_published_as_complete(self):
        application = {"key": "critical-app", "criticality": "critical", "maturityLevel": "production"}
        detail = {
            **application,
            "versionsConnection": {
                "totalCount": 101,
                "edges": [{"node": {"version": "1", "promotionsConnection": {"totalCount": 0, "edges": [], "pageInfo": {"hasNextPage": False}}, "evidenceSubject": {"evidenceConnection": {"totalCount": 0, "edges": [], "pageInfo": {"hasNextPage": False}}}}}],
                "pageInfo": {"hasNextPage": True, "endCursor": "next"},
            },
        }
        client = FakeClient([{"data": {"applications": {"app0": detail}}}])
        with self.assertRaisesRegex(RuntimeError, "refuses a partial"):
            APPTRUST.collect_details(client, [application])

    def test_summary_preserves_ownership_release_and_evidence_counts(self):
        applications = [
            {"key": "a", "projectKey": "P", "criticality": "critical", "maturityLevel": "production", "owners": []},
            {"key": "b", "projectKey": "P", "criticality": "high", "maturityLevel": "experimental", "owners": [{"name": "team"}]},
        ]
        details = [{**applications[0], "versionsConnection": {"edges": [{"node": {
            "version": "1", "currentStageName": "PROD", "releaseStatus": "TRUSTED_RELEASE",
            "promotionsConnection": {"edges": [{"node": {"status": "FAILED"}}]},
            "evidenceSubject": {"evidenceConnection": {"edges": [{"node": {"predicateSlug": "release-gate", "verified": False}}]}},
        }}]}}]
        value = APPTRUST.summarize(applications, details, 1)
        self.assertEqual(value["inventory"]["critical_unowned"], 1)
        self.assertEqual(value["release_governance"]["trusted_releases"], 1)
        self.assertEqual(value["release_governance"]["promotion_status"]["FAILED"], 1)
        self.assertEqual(value["evidence"]["unverified"], 1)
        self.assertEqual(value["evidence"]["gate_certifications"], 1)


if __name__ == "__main__":
    unittest.main()
