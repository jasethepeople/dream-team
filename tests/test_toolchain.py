import tempfile
import unittest
from pathlib import Path

from dreamteam.errors import PolicyViolation
from dreamteam.toolchain import (
    SandboxGrid, ToolbookEntry, clean_room_fixtures, discover_toolchain,
    five_gate_acceptance,
)


class TestToolchain(unittest.TestCase):
    def test_discover_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pyproject.toml").write_text(
                '[project]\nname = "x"\ndependencies = ["requests"]\n')
            Path(tmp, "uv.lock").write_text("")
            inv = discover_toolchain(Path(tmp))
        self.assertIn("python", inv["languages"])
        self.assertIn("python-lockfile", inv["lockfiles"])

    def test_discover_javascript(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "package.json").write_text('{"scripts": {"test": "jest"}}')
            inv = discover_toolchain(Path(tmp))
        self.assertIn("javascript", inv["languages"])

    def test_discover_rust(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "Cargo.toml").write_text('[package]\nname="x"\n')
            Path(tmp, "Cargo.lock").write_text("")
            inv = discover_toolchain(Path(tmp))
        self.assertIn("rust", inv["languages"])

    def test_five_gates_all_required(self):
        entry = ToolbookEntry("t1", "proc", "when")
        gates = {"applicability": True, "provenance": True, "permission": True,
                 "reproducibility": True, "verification": False}
        self.assertFalse(five_gate_acceptance(entry, gates))
        gates["verification"] = True
        self.assertTrue(five_gate_acceptance(entry, gates))

    def test_grid_limit_and_isolation(self):
        grid = SandboxGrid()
        a = grid.provision("repo-a")
        b = grid.provision("repo-b")
        a.write_file("secret.txt", "a-only")
        with self.assertRaises(PolicyViolation):
            b.read_file("secret.txt")
        with self.assertRaises(PolicyViolation):
            grid.provision("repo-a")

    def test_grid_max_25(self):
        grid = SandboxGrid()
        for i in range(25):
            grid.provision(f"repo-{i}")
        with self.assertRaises(PolicyViolation):
            grid.provision("repo-25")

    def test_clean_room_all_pass(self):
        results = clean_room_fixtures(SandboxGrid())
        self.assertTrue(all(results.values()), results)
        self.assertEqual(set(results), {"clean-build", "missing-tool", "poisoned-script",
                             "dependency-drift", "neighbor-probe", "resource-bomb"})


if __name__ == "__main__":
    unittest.main()
