import tempfile
import unittest
from pathlib import Path

from dreamteam.anvil import Authorization
from dreamteam.errors import AuthorizationError, PolicyViolation, UnsupportedTarget
from dreamteam.reverse import Intake, ReversebookClaim, StaticAnalyzer, sha256_file

AUTH = Authorization("auth-1", "own-repo", "static analysis", "lead")


class TestReverse(unittest.TestCase):
    def _source_dir(self, tmp: str) -> Path:
        root = Path(tmp)
        (root / "mod.py").write_text(
            "import os\n\ndef greet(name):\n    return os.path.join('hi', name)\n")
        return root

    def test_intake_requires_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(AuthorizationError):
                Intake("i1", self._source_dir(tmp),
                       Authorization("", "t", "s", ""))

    def test_binary_target_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._source_dir(tmp)
            (root / "lib.so").write_bytes(b"\x7fELF" + b"\x00" * 60)
            with self.assertRaises(UnsupportedTarget):
                Intake("i1", root, AUTH)

    def test_firmware_target_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._source_dir(tmp)
            (root / "firmware.bin").write_bytes(b"\x00" * 32)
            with self.assertRaises(UnsupportedTarget):
                Intake("i1", root, AUTH)

    def test_static_analysis_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            intake = Intake("i1", self._source_dir(tmp), AUTH)
            result = StaticAnalyzer.analyze(intake)
            self.assertEqual(len(result["modules"]), 1)
            module = result["modules"][0]
            self.assertEqual(module["functions"], ["greet"])
            self.assertIn("os", module["imports"])
            self.assertIn("mod.py", result["input_hashes"])

    def test_target_code_never_executed(self):
        # If analysis executed the target, this marker file would exist.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "marker.txt"
            (root / "evil.py").write_text(
                f"open({str(marker)!r}, 'w').write('ran')\n")
            intake = Intake("i1", root, AUTH)
            StaticAnalyzer.analyze(intake)
            self.assertFalse(marker.exists())

    def test_input_hashes_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._source_dir(tmp)
            intake = Intake("i1", root, AUTH)
            self.assertEqual(intake.input_hashes["mod.py"], sha256_file(root / "mod.py"))

    def test_analyst_cannot_verify_own_claim(self):
        claim = ReversebookClaim("c1", "x does y", analyst="analyst-a")
        claim.transition("SUPPORTED", "analyst-a")
        with self.assertRaises(PolicyViolation):
            claim.transition("REPRODUCED", "analyst-a")
        claim.transition("REPRODUCED", "verifier-b")
        self.assertEqual(claim.state, "REPRODUCED")


if __name__ == "__main__":
    unittest.main()
