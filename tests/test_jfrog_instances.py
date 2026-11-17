import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("instances", ROOT / "scripts" / "list_jfrog_instances.py")
INSTANCES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTANCES)


class JFrogInstanceTests(unittest.TestCase):
    def test_parses_all_instances_and_default(self):
        value = INSTANCES.parse_config_show("""
Server ID: LiquidJedi
JFrog Platform URL: https://liquidjedi.jfrog.io/
Default: true

Server ID: solenglatest
JFrog Platform URL: https://solenglatest.jfrog.io/
Default: false
""")
        self.assertEqual([row["id"] for row in value], ["LiquidJedi", "solenglatest"])
        self.assertTrue(value[0]["default"])
        self.assertFalse(value[1]["default"])


if __name__ == "__main__":
    unittest.main()
