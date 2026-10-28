import unittest

from dreamteam.archive import Archive
from dreamteam.errors import PolicyViolation

GOOD = {"event_id": "evt-1", "project_id": "p", "event_type": "build",
        "actor": "ci", "inputs": {}, "outputs": {}, "claim": "built",
        "verification": {"method": "replay"}, "retention_class": "standard"}


class TestArchive(unittest.TestCase):
    def test_record_and_verify(self):
        archive = Archive()
        archive.record(dict(GOOD), "ci")
        archive.verify()

    def test_missing_field_rejected(self):
        archive = Archive()
        bad = dict(GOOD)
        del bad["claim"]
        with self.assertRaises(PolicyViolation):
            archive.record(bad, "ci")

    def test_burned_rule_never_returns(self):
        archive = Archive()
        archive.propose_rule("r1", "pin deps")
        archive.transition_rule("r1", "TESTED", "a")
        archive.transition_rule("r1", "BURNED", "a")
        with self.assertRaises(PolicyViolation):
            archive.transition_rule("r1", "STANDARD", "a")
        with self.assertRaises(PolicyViolation):
            archive.check_rule_usable("r1")

    def test_release_gate_blocks_missing_evidence(self):
        archive = Archive()
        archive.record(dict(GOOD), "ci")
        with self.assertRaises(PolicyViolation):
            archive.release_gate(["evt-1", "evt-missing"])
        archive.release_gate(["evt-1"])

    def test_tampered_ledger_detected(self):
        archive = Archive()
        archive.record(dict(GOOD), "ci")
        archive.ledger.events[0]["payload"]["claim"] = "forged"
        with self.assertRaises(Exception):
            archive.verify()


if __name__ == "__main__":
    unittest.main()
