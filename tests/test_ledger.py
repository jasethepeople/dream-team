import json
import tempfile
import unittest
from pathlib import Path

from dreamteam.ledger import Ledger, LedgerError, generate_keypair


class TestLedger(unittest.TestCase):
    def test_append_and_verify(self):
        ledger = Ledger()
        ledger.append("build", {"event_id": "e1"}, "builder")
        ledger.append("test", {"event_id": "e2"}, "qa")
        ledger.verify()
        self.assertEqual([e["seq"] for e in ledger.events], [0, 1])
        self.assertEqual(ledger.events[1]["prev"], ledger.events[0]["sig"])

    def test_tamper_detected(self):
        ledger = Ledger()
        ledger.append("build", {"event_id": "e1"}, "builder")
        ledger.events[0]["payload"]["event_id"] = "forged"
        with self.assertRaises(LedgerError):
            ledger.verify()

    def test_reorder_detected(self):
        ledger = Ledger()
        ledger.append("a", {}, "x")
        ledger.append("b", {}, "x")
        events = [ledger.events[1], ledger.events[0]]
        with self.assertRaises(LedgerError):
            Ledger(events)

    def test_jsonl_roundtrip(self):
        ledger = Ledger()
        ledger.append("build", {"event_id": "e1"}, "builder")
        restored = Ledger.from_jsonl(ledger.to_jsonl())
        restored.verify()
        self.assertEqual(len(restored.events), 1)

    def test_checkpoint_sign_and_verify(self):
        ledger = Ledger()
        ledger.append("build", {"event_id": "e1"}, "builder")
        with tempfile.TemporaryDirectory() as tmp:
            priv, pub = Path(tmp) / "k.pem", Path(tmp) / "k.pub"
            generate_keypair(priv, pub)
            anchor = ledger.checkpoint("phase-0", priv, pub)
            ledger.verify_anchor(anchor, pub)

    def test_tampered_anchor_rejected(self):
        ledger = Ledger()
        ledger.append("build", {"event_id": "e1"}, "builder")
        with tempfile.TemporaryDirectory() as tmp:
            priv, pub = Path(tmp) / "k.pem", Path(tmp) / "k.pub"
            generate_keypair(priv, pub)
            anchor = ledger.checkpoint("phase-0", priv, pub)
            anchor["head_sig"] = "f" * 64
            with self.assertRaises(LedgerError):
                ledger.verify_anchor(anchor, pub)

    def test_keypair_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            priv, pub = Path(tmp) / "k.pem", Path(tmp) / "k.pub"
            generate_keypair(priv, pub)
            with self.assertRaises(LedgerError):
                generate_keypair(priv, pub)

    def test_rewritten_chain_fails_against_checkpoint(self):
        # Rewriting history and recomputing hashes must not pass an
        # anchor signed over the original head.
        ledger = Ledger()
        ledger.append("build", {"event_id": "e1"}, "builder")
        with tempfile.TemporaryDirectory() as tmp:
            priv, pub = Path(tmp) / "k.pem", Path(tmp) / "k.pub"
            generate_keypair(priv, pub)
            anchor = ledger.checkpoint("phase-0", priv, pub)
            forged = Ledger()
            forged.append("build", {"event_id": "forged"}, "builder")
            with self.assertRaises(LedgerError):
                forged.verify_anchor(anchor, pub)


if __name__ == "__main__":
    unittest.main()
