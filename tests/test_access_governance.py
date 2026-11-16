import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "collect_access_governance.py"
SPEC = importlib.util.spec_from_file_location("collect_access_governance", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AccessGovernanceTests(unittest.TestCase):
    def test_token_summary_does_not_invent_expired_history(self):
        now = 1_000_000
        payload = {"tokens": [
            {"token_id": "secret-token-id", "subject": "ci-bot", "description": "release", "expiry": now + 2 * 86400, "issued_at": now - 10, "last_used": 0, "refreshable": False},
            {"expiry": None, "issued_at": now - 40 * 86400, "last_used": now - 5, "refreshable": True},
        ]}
        result = MODULE.token_summary(payload, now)
        self.assertEqual(result["listed_active"], 2)
        self.assertEqual(result["expires_within_7_days"], 1)
        self.assertEqual(result["non_expiring"], 1)
        self.assertEqual(result["issued_last_7_days"], 1)
        self.assertEqual(len(result["rotation_queue"]), 1)
        self.assertEqual(result["rotation_queue"][0]["owner"], "ci-bot")
        self.assertNotEqual(result["rotation_queue"][0]["reference"], "secret-token-id")
        self.assertNotIn("token_id", result["rotation_queue"][0])
        self.assertIsNone(result["expired"])

    def test_oidc_repository_claims_are_explicit(self):
        provider = {"name": "ci", "provider_type": "GitHub"}
        rows = MODULE.mapping_rows(provider, [{
            "name": "repo-map",
            "claims": {"repository": "acme/widgets", "ref": "refs/heads/main"},
            "token_spec": {"expires_in": 600},
        }])
        self.assertEqual(rows[0]["provider_family"], "GitHub")
        self.assertEqual(rows[0]["repository_claims"], [{"claim": "repository", "pattern": "acme/widgets"}])
        self.assertEqual(rows[0]["token_ttl_seconds"], 600)


if __name__ == "__main__":
    unittest.main()
