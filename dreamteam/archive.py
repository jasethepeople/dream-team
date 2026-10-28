"""Evidence & Archive (Doc 2): canonical events, doctrine lifecycle, gates.

Wraps the signed Ledger with the Doc 2 event contract (required
fields), the MOLT doctrine lifecycle (PROPOSED -> TESTED ->
STANDARD / BURNED / DEPRECATED / SUPERSEDED), and a policy gate:
a BURNED rule can never silently return to active status, and a
release with missing or invalid evidence is refused.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import PolicyViolation
from .ledger import Ledger, verify_events

REQUIRED_EVENT_FIELDS = {
    "event_id", "project_id", "event_type", "actor",
    "inputs", "outputs", "claim", "verification", "retention_class",
}
RETENTION_CLASSES = {"permanent", "standard", "ephemeral"}

DOCTRINE_TRANSITIONS = {
    "PROPOSED": {"TESTED", "DEPRECATED"},
    "TESTED": {"STANDARD", "BURNED", "DEPRECATED"},
    "STANDARD": {"SUPERSEDED", "BURNED", "DEPRECATED"},
    "BURNED": set(),  # terminal: a burned rule never returns to active use
    "DEPRECATED": set(),
    "SUPERSEDED": set(),
}
ACTIVE_STATES = {"PROPOSED", "TESTED", "STANDARD"}


def validate_event_payload(payload: dict[str, Any]) -> None:
    missing = REQUIRED_EVENT_FIELDS - set(payload)
    if missing:
        raise PolicyViolation(f"event payload missing required fields: {sorted(missing)}")
    if payload["retention_class"] not in RETENTION_CLASSES:
        raise PolicyViolation(f"unknown retention_class: {payload['retention_class']!r}")


@dataclass
class DoctrineRule:
    rule_id: str
    text: str
    state: str = "PROPOSED"
    supersedes: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)

    def transition(self, new_state: str, actor: str) -> None:
        allowed = DOCTRINE_TRANSITIONS[self.state]
        if new_state not in allowed:
            raise PolicyViolation(
                f"doctrine transition {self.state} -> {new_state} is forbidden")
        if new_state == "SUPERSEDED" and not self.supersedes:
            raise PolicyViolation("SUPERSEDED requires a replacement rule id")
        self.history.append(f"{self.state}->{new_state} by {actor}")
        self.state = new_state


class Archive:
    """The archive: signed events plus doctrine, backed by a Ledger."""

    def __init__(self) -> None:
        self.ledger = Ledger()
        self.rules: dict[str, DoctrineRule] = {}

    def record(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        validate_event_payload(payload)
        return self.ledger.append(payload["event_type"], payload, actor)

    def verify(self) -> None:
        self.ledger.verify()
        verify_events(self.ledger.events)

    def propose_rule(self, rule_id: str, text: str) -> DoctrineRule:
        if rule_id in self.rules:
            raise PolicyViolation(f"rule {rule_id!r} already exists")
        rule = DoctrineRule(rule_id=rule_id, text=text)
        self.rules[rule_id] = rule
        return rule

    def transition_rule(self, rule_id: str, new_state: str, actor: str) -> DoctrineRule:
        rule = self.rules[rule_id]
        rule.transition(new_state, actor)
        self.ledger.append("doctrine_transition",
                           {"rule_id": rule_id, "new_state": new_state}, actor)
        return rule

    def check_rule_usable(self, rule_id: str) -> None:
        """Policy gate: burned/deprecated/superseded rules must not be applied."""
        rule = self.rules[rule_id]
        if rule.state == "BURNED":
            raise PolicyViolation(
                f"rule {rule_id!r} is BURNED and must not be applied; "
                "adjudication required")
        if rule.state not in ACTIVE_STATES:
            raise PolicyViolation(f"rule {rule_id!r} is {rule.state}, not active")

    def release_gate(self, required_event_ids: list[str]) -> None:
        """No trusted release status when required evidence is missing."""
        self.verify()
        present = {e["payload"].get("event_id") for e in self.ledger.events}
        missing = [e for e in required_event_ids if e not in present]
        if missing:
            raise PolicyViolation(f"release blocked: missing evidence events {missing}")
