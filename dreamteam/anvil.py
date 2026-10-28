"""Adversarial / Security Team — The Anvil (Doc 3), RE-SCOPED.

Defensive adversarial evaluation only, under the binding RE-SCOPE:
- engagements require a written authorization record (scope, target,
  approver) before any check runs;
- boundary checks are fixtures asserting the MockSandbox DENIES an
  attempt; no escape technique is implemented or attempted;
- SAST-style checks, dependency/pin checks, secret-pattern scans,
  and malformed-input tests run against the team's OWN code and
  fixtures only;
- no exploit development, no exploit-reproduction pipeline, no
  abuse-potential research catalog;
- finding lifecycle enforces separation: the finder never certifies
  its own fix; VERIFIED_FIXED needs independent retest evidence
  from a different actor;
- stop-work: any real escape, credential exposure, or unexpected
  egress raises StopWork and halts the engagement.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import AuthorizationError, PolicyViolation
from .sandbox import MockSandbox

FINDING_TRANSITIONS = {
    "SUSPECTED": {"CONFIRMED", "CLOSED"},
    "CONFIRMED": {"ACCEPTED", "CLOSED"},
    "ACCEPTED": {"FIXED_PENDING_RETEST"},
    "FIXED_PENDING_RETEST": {"VERIFIED_FIXED", "ACCEPTED"},
    "VERIFIED_FIXED": {"CLOSED"},
    "CLOSED": set(),
}
SEVERITIES = {"Critical", "High", "Medium", "Low", "Informational"}
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password)\s*=\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)ghp_[A-Za-z0-9]{20,}"),
]


class StopWork(PolicyViolation):
    """A stop-work condition fired; the engagement halts immediately."""


@dataclass
class Authorization:
    authorization_id: str
    target: str
    scope: str
    approver: str
    approved: bool = True

    def require(self) -> None:
        if not self.approved or not self.authorization_id or not self.approver:
            raise AuthorizationError("engagement requires an approved authorization record")


@dataclass
class Finding:
    finding_id: str
    severity: str
    title: str
    state: str = "SUSPECTED"
    finder: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    retest_actor: str = ""

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise PolicyViolation(f"unknown severity: {self.severity!r}")

    def transition(self, new_state: str, actor: str,
                   retest_evidence: list[str] | None = None) -> None:
        if new_state not in FINDING_TRANSITIONS[self.state]:
            raise PolicyViolation(f"finding transition {self.state} -> {new_state} forbidden")
        if new_state == "VERIFIED_FIXED":
            if actor == self.finder:
                raise PolicyViolation("finder cannot certify its own fix")
            if not retest_evidence:
                raise PolicyViolation("VERIFIED_FIXED requires independent retest evidence")
            self.retest_actor = actor
            self.evidence_refs.extend(retest_evidence)
        self.state = new_state


@dataclass
class Engagement:
    engagement_id: str
    authorization: Authorization
    sandbox: MockSandbox

    def __post_init__(self) -> None:
        self.authorization.require()


def scan_secrets(text: str) -> list[str]:
    """Secret-pattern scan over the team's own artifacts (defensive)."""
    hits = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern[:40])
    return hits


def check_dependency_pins(manifest: dict[str, str]) -> list[str]:
    """Every dependency must carry an exact pinned version."""
    unpinned = [name for name, version in manifest.items()
                if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version or "")]
    return unpinned


def boundary_fixture(sandbox: MockSandbox) -> dict[str, bool]:
    """Assert the sandbox denies each boundary attempt. All must hold.

    These are denial assertions, not escape attempts: each probe is
    a forbidden action the sandbox must refuse.
    """
    probes = {
        "read_outside_workspace": lambda: sandbox.read_file("../host-secret.txt"),
        "read_other_job": lambda: sandbox.read_file("other-job/notes.txt"),
        "read_sensitive_name": lambda: sandbox.read_file("id_rsa"),
        "network_egress": lambda: sandbox.network_fetch("https://example.invalid/"),
    }
    results = {}
    for name, probe in probes.items():
        try:
            probe()
            results[name] = False  # a successful probe means the boundary failed
        except PolicyViolation:
            results[name] = True
    return results


def fuzz_validator(validator: Callable[[Any], bool], inputs: list[Any]) -> list[Any]:
    """Feed malformed inputs to the team's own validator; collect crashes.

    A crash (unexpected exception) is a finding; a clean True/False
    for every input is a pass. No target code is executed.
    """
    crashes = []
    for value in inputs:
        try:
            validator(value)
        except Exception:
            crashes.append(value)
    return crashes


class ReleaseGate:
    """Blocks release while Critical/High findings are unresolved."""

    @staticmethod
    def decide(findings: list[Finding], exceptions: list[dict[str, Any]] | None = None) -> str:
        open_blockers = [f for f in findings
                         if f.severity in ("Critical", "High") and f.state != "CLOSED"]
        if not open_blockers:
            return "pass"
        exc = exceptions or []
        excused = {e["finding_id"] for e in exc if e.get("risk_owner") and e.get("expires")}
        if all(f.finding_id in excused for f in open_blockers):
            return "pass_with_authorized_exception"
        return "blocked"
