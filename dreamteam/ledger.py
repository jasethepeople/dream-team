"""Signed append-only ledger (MOLT-style) for the Dream Team.

Pattern reused from the Redbook anchor design (read-only prior art):
canonical JSON serialization, SHA-256 hash chain over events, and
Ed25519 signatures made with the OpenSSL CLI (``pkeyutl``), so the
package needs no third-party cryptography dependency. A hash chain
alone is not treated as sufficient: signed checkpoints (anchors)
bind the head of the chain to a key held outside the ledger.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .errors import DreamTeamError

ZERO_HASH = "0" * 64
EVENT_FIELDS = {"seq", "ts", "type", "payload", "actor", "prev", "sig"}
ANCHOR_FIELDS = {"seq", "head_sig", "phase", "prev_anchor_sig", "ts", "sig"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class LedgerError(DreamTeamError):
    pass


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise LedgerError("value is not valid canonical JSON") from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LedgerError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def event_signature(event: dict[str, Any]) -> str:
    body = {key: event[key] for key in ("seq", "ts", "type", "payload", "actor", "prev")}
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def verify_events(events: list[dict[str, Any]]) -> None:
    if not isinstance(events, list):
        raise LedgerError("ledger must be a JSON array of events")
    previous = ZERO_HASH
    previous_ts: int | None = None
    for index, event in enumerate(events):
        if not isinstance(event, dict) or set(event) != EVENT_FIELDS:
            raise LedgerError(f"event {index} has missing or unexpected fields")
        if isinstance(event["seq"], bool) or not isinstance(event["seq"], int) or event["seq"] != index:
            raise LedgerError(f"event sequence mismatch at index {index}")
        if isinstance(event["ts"], bool) or not isinstance(event["ts"], int) or event["ts"] < 0:
            raise LedgerError(f"event {index} timestamp is not a non-negative integer")
        if previous_ts is not None and event["ts"] < previous_ts:
            raise LedgerError(f"event timestamps go backwards at sequence {index}")
        if not isinstance(event["type"], str) or not event["type"]:
            raise LedgerError(f"event {index} has an invalid type")
        if not isinstance(event["payload"], dict) or not isinstance(event["actor"], str) or not event["actor"]:
            raise LedgerError(f"event {index} has an invalid payload or actor")
        if event["prev"] != previous:
            raise LedgerError(f"previous-event hash mismatch at sequence {index}")
        if not isinstance(event["sig"], str) or not HEX64.fullmatch(event["sig"]):
            raise LedgerError(f"event {index} has an invalid hash")
        if event["sig"] != event_signature(event):
            raise LedgerError(f"event hash mismatch at sequence {index}")
        previous, previous_ts = event["sig"], event["ts"]


def _openssl() -> str:
    executable = shutil.which("openssl")
    if not executable:
        raise LedgerError("OpenSSL is required but was not found on PATH")
    return executable


def _run_openssl(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([_openssl(), *args], capture_output=True, text=True)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "OpenSSL command failed"
        raise LedgerError(detail)
    return result


def generate_keypair(private_path: Path, public_path: Path) -> None:
    """Generate an Ed25519 keypair. Refuses to overwrite existing files."""
    if private_path.resolve() == public_path.resolve():
        raise LedgerError("private and public key paths must be different")
    if private_path.exists() or public_path.exists():
        raise LedgerError("refusing to overwrite an existing key file")
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    previous_umask = os.umask(0o077)
    try:
        _run_openssl(["genpkey", "-algorithm", "ED25519", "-out", str(private_path)])
        os.chmod(private_path, 0o600)
        _run_openssl(["pkey", "-in", str(private_path), "-pubout", "-out", str(public_path)])
    except Exception:
        private_path.unlink(missing_ok=True)
        public_path.unlink(missing_ok=True)
        raise
    finally:
        os.umask(previous_umask)


def _sign(private_path: Path, message: bytes) -> bytes:
    with tempfile.TemporaryDirectory(prefix="dreamteam-sign-") as directory:
        source = Path(directory) / "message.bin"
        signature = Path(directory) / "signature.bin"
        source.write_bytes(message)
        _run_openssl(["pkeyutl", "-sign", "-inkey", str(private_path),
                      "-rawin", "-in", str(source), "-out", str(signature)])
        return signature.read_bytes()


def _verify_signature(public_path: Path, message: bytes, signature: bytes) -> bool:
    if len(signature) != 64:
        return False
    with tempfile.TemporaryDirectory(prefix="dreamteam-verify-") as directory:
        source = Path(directory) / "message.bin"
        sig_file = Path(directory) / "signature.bin"
        source.write_bytes(message)
        sig_file.write_bytes(signature)
        result = subprocess.run(
            [_openssl(), "pkeyutl", "-verify", "-pubin", "-inkey", str(public_path),
             "-rawin", "-in", str(source), "-sigfile", str(sig_file)],
            capture_output=True, text=True,
        )
        return result.returncode == 0


def anchor_signature(anchor: dict[str, Any]) -> str:
    body = {key: anchor[key] for key in ("seq", "head_sig", "phase", "prev_anchor_sig", "ts")}
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


class Ledger:
    """Append-only signed event ledger with Ed25519 checkpoints."""

    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self.events: list[dict[str, Any]] = list(events) if events else []
        verify_events(self.events)
        self.anchors: list[dict[str, Any]] = []

    def append(self, event_type: str, payload: dict[str, Any], actor: str,
               ts: int | None = None) -> dict[str, Any]:
        if not event_type or not isinstance(event_type, str):
            raise LedgerError("event type must be a non-empty string")
        if not isinstance(payload, dict):
            raise LedgerError("event payload must be an object")
        if not actor or not isinstance(actor, str):
            raise LedgerError("event actor must be a non-empty string")
        timestamp = int(time.time()) if ts is None else ts
        if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp < 0:
            raise LedgerError("event timestamp must be a non-negative integer")
        if self.events and timestamp < self.events[-1]["ts"]:
            raise LedgerError("event timestamp precedes the previous event")
        event = {
            "seq": len(self.events),
            "ts": timestamp,
            "type": event_type,
            "payload": payload,
            "actor": actor,
            "prev": self.events[-1]["sig"] if self.events else ZERO_HASH,
        }
        event["sig"] = event_signature(event)
        self.events.append(event)
        return event

    def verify(self) -> None:
        verify_events(self.events)

    def head_sig(self) -> str:
        return self.events[-1]["sig"] if self.events else ZERO_HASH

    def checkpoint(self, phase: str, private_path: Path, public_path: Path,
                   ts: int | None = None) -> dict[str, Any]:
        """Sign an anchor over the current head. Returns the anchor dict."""
        timestamp = int(time.time()) if ts is None else ts
        anchor = {
            "seq": len(self.events) - 1,
            "head_sig": self.head_sig(),
            "phase": phase,
            "prev_anchor_sig": self.anchors[-1]["sig"] if self.anchors else ZERO_HASH,
            "ts": timestamp,
        }
        message = canonical_bytes({**anchor, "sig": anchor_signature(anchor)})
        import base64
        anchor["sig"] = base64.b64encode(_sign(private_path, message)).decode("ascii")
        self.anchors.append(anchor)
        return anchor

    def verify_anchor(self, anchor: dict[str, Any], public_path: Path) -> None:
        if set(anchor) != ANCHOR_FIELDS:
            raise LedgerError("anchor has missing or unexpected fields")
        if anchor["head_sig"] != self.head_sig():
            raise LedgerError("anchor head does not match ledger head")
        if anchor["seq"] != len(self.events) - 1 and not (not self.events and anchor["seq"] == -1):
            raise LedgerError("anchor sequence does not match ledger length")
        import base64
        message = canonical_bytes({**anchor, "sig": anchor_signature(anchor)})
        try:
            signature = base64.b64decode(anchor["sig"], validate=True)
        except Exception as exc:
            raise LedgerError("anchor signature is not valid base64") from exc
        if not _verify_signature(public_path, message, signature):
            raise LedgerError("anchor signature verification failed")

    def to_jsonl(self) -> str:
        verify_events(self.events)
        return "".join(
            json.dumps(event, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n"
            for event in self.events
        )

    @classmethod
    def from_jsonl(cls, text: str) -> "Ledger":
        events: list[dict[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                raise LedgerError(f"blank line in ledger at line {line_number}")
            try:
                event = json.loads(line, object_pairs_hook=_unique_object)
            except json.JSONDecodeError as exc:
                raise LedgerError(f"invalid ledger JSON on line {line_number}: {exc}") from exc
            events.append(event)
        return cls(events)
