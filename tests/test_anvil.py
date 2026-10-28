import unittest

from dreamteam.anvil import (
    Authorization, Engagement, Finding, ReleaseGate, boundary_fixture,
    check_dependency_pins, fuzz_validator, scan_secrets,
)
from dreamteam.errors import AuthorizationError, PolicyViolation
from dreamteam.sandbox import MockSandbox


class TestAnvil(unittest.TestCase):
    def test_engagement_requires_authorization(self):
        with self.assertRaises(AuthorizationError):
            Engagement("e1", Authorization("", "t", "s", ""), MockSandbox("j"))
        with self.assertRaises(AuthorizationError):
            Engagement("e1", Authorization("a", "t", "s", "lead", approved=False),
                       MockSandbox("j"))

    def test_boundary_fixture_all_denied(self):
        results = boundary_fixture(MockSandbox("job-1"))
        self.assertTrue(all(results.values()), results)

    def test_secret_scan_flags_own_artifacts(self):
        hits = scan_secrets('api_key = "sk-1234567890abcdef"')
        self.assertTrue(hits)
        self.assertEqual(scan_secrets("no secrets here"), [])

    def test_dependency_pins(self):
        self.assertEqual(check_dependency_pins({"a": "1.2.3"}), [])
        self.assertEqual(check_dependency_pins({"a": "*"}), ["a"])

    def test_fuzz_validator_reports_crashes(self):
        def validator(value):
            if not isinstance(value, int):
                raise TypeError("not int")
            return value > 0
        self.assertEqual(fuzz_validator(validator, [1, "x", None]), ["x", None])
        self.assertEqual(fuzz_validator(validator, [1, 2]), [])

    def test_finder_cannot_certify_own_fix(self):
        finding = Finding("f1", "High", "x", finder="finder-a")
        finding.transition("CONFIRMED", "finder-a")
        finding.transition("ACCEPTED", "finder-a")
        finding.transition("FIXED_PENDING_RETEST", "finder-a")
        with self.assertRaises(PolicyViolation):
            finding.transition("VERIFIED_FIXED", "finder-a", ["retest-1"])
        finding.transition("VERIFIED_FIXED", "verifier-b", ["retest-1"])
        self.assertEqual(finding.state, "VERIFIED_FIXED")

    def test_release_gate_blocks_open_critical(self):
        finding = Finding("f1", "Critical", "x", state="CONFIRMED")
        self.assertEqual(ReleaseGate.decide([finding]), "blocked")
        finding.transition("CLOSED", "lead")
        self.assertEqual(ReleaseGate.decide([finding]), "pass")


if __name__ == "__main__":
    unittest.main()
