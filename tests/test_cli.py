import json
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestCli(unittest.TestCase):
    def test_cli_smoke_all(self):
        result = subprocess.run(
            [sys.executable, "-m", "dreamteam.cli", "all", "smoke"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(set(report), {"ledger", "foundry", "archive", "anvil",
                                "deploy", "repair", "engine", "toolchain",
                                "reverse", "team"})
        for name, entry in report.items():
            self.assertNotIn("error", entry, f"{name}: {entry}")

    def test_cli_smoke_engine_stops_at_manual_assist(self):
        result = subprocess.run(
            [sys.executable, "-m", "dreamteam.cli", "engine", "smoke"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=60)
        report = json.loads(result.stdout)
        self.assertEqual(report["engine"]["status"], "manual_assist")


if __name__ == "__main__":
    unittest.main()
