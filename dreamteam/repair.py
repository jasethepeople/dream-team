"""Repair / RUNBOOK Team (Doc 5): diagnose before changing, authorize
before acting, verify before closing.

Risk classes R0 (read-only) through R3 (destructive). R2/R3 actions
require an explicit approval record; applying without one raises.
Diagnosis is read-only against mock environments; the verifier is a
different actor from the executor. A repair is RECOVERED only when
the original failing check passes again.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import AuthorizationError, PolicyViolation
from .ledger import Ledger

STATES = ("DETECTED", "DIAGNOSING", "PLAN_READY", "AWAITING_APPROVAL",
          "REPAIRING", "VERIFYING", "RECOVERED", "PARTIALLY_RECOVERED",
          "FAILED_OR_ROLLED_BACK")
TRANSITIONS = {
    "DETECTED": {"DIAGNOSING"},
    "DIAGNOSING": {"PLAN_READY", "FAILED_OR_ROLLED_BACK"},
    "PLAN_READY": {"AWAITING_APPROVAL", "REPAIRING"},
    "AWAITING_APPROVAL": {"REPAIRING", "FAILED_OR_ROLLED_BACK"},
    "REPAIRING": {"VERIFYING", "FAILED_OR_ROLLED_BACK"},
    "VERIFYING": {"RECOVERED", "PARTIALLY_RECOVERED", "FAILED_OR_ROLLED_BACK"},
    "RECOVERED": set(),
    "PARTIALLY_RECOVERED": set(),
    "FAILED_OR_ROLLED_BACK": set(),
}
RISK_APPROVAL = {"R0": False, "R1": False, "R2": True, "R3": True}


@dataclass
class Approval:
    approval_id: str
    approver: str
    scope: str


@dataclass
class RepairPlan:
    plan_id: str
    diagnosis: str
    actions: list[dict[str, Any]]  # each: {name, risk, apply: callable-name}
    approval: Approval | None = None

    def max_risk(self) -> str:
        order = ["R0", "R1", "R2", "R3"]
        worst = "R0"
        for action in self.actions:
            if order.index(action["risk"]) > order.index(worst):
                worst = action["risk"]
        return worst

    def requires_approval(self) -> bool:
        return RISK_APPROVAL[self.max_risk()]


class MockEnvironment:
    """A mock broken environment with checkable health and fixable faults."""

    def __init__(self, faults: dict[str, bool] | None = None) -> None:
        self.faults = dict(faults or {})
        self.log: list[str] = []

    def check(self, name: str) -> bool:
        """True means the check passes (no fault). Read-only."""
        return not self.faults.get(name, False)

    def fix(self, name: str) -> None:
        self.faults[name] = False
        self.log.append(f"fixed:{name}")


@dataclass
class Incident:
    incident_id: str
    target: str
    symptom: str
    state: str = "DETECTED"
    diagnosis: str = ""
    plan: RepairPlan | None = None
    evidence: list[str] = field(default_factory=list)

    def move(self, new_state: str) -> None:
        if new_state not in TRANSITIONS[self.state]:
            raise PolicyViolation(f"incident transition {self.state} -> {new_state} forbidden")
        self.state = new_state


class RepairTeam:
    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger

    def diagnose(self, incident: Incident, env: MockEnvironment,
                 checks: list[str]) -> str:
        incident.move("DIAGNOSING")
        failing = [c for c in checks if not env.check(c)]
        incident.diagnosis = (f"failing checks: {failing}" if failing
                             else "no failing checks; symptom not reproduced")
        incident.evidence.append(incident.diagnosis)
        return incident.diagnosis

    def plan_repair(self, incident: Incident,
                    actions: list[dict[str, Any]]) -> RepairPlan:
        plan = RepairPlan(plan_id=f"plan-{incident.incident_id}",
                          diagnosis=incident.diagnosis, actions=actions)
        incident.plan = plan
        incident.move("PLAN_READY")
        return plan

    def apply_repair(self, incident: Incident, env: MockEnvironment,
                     executor: str, approval: Approval | None = None) -> None:
        if incident.plan is None:
            raise PolicyViolation("no repair plan exists")
        if incident.plan.requires_approval():
            if approval is None:
                incident.move("AWAITING_APPROVAL")
                raise AuthorizationError(
                    f"plan risk {incident.plan.max_risk()} requires explicit approval")
            incident.plan.approval = approval
        incident.move("REPAIRING")
        for action in incident.plan.actions:
            env.fix(action["name"])
            incident.evidence.append(f"applied:{action['name']} by {executor}")
        self.ledger.append("repair_applied",
                           {"incident_id": incident.incident_id,
                            "plan_id": incident.plan.plan_id}, executor)

    def verify(self, incident: Incident, env: MockEnvironment, checks: list[str],
               verifier: str, executor: str) -> str:
        if verifier == executor:
            raise PolicyViolation("verifier must differ from executor")
        incident.move("VERIFYING")
        failing = [c for c in checks if not env.check(c)]
        if not failing:
            incident.move("RECOVERED")
        elif len(failing) < len(checks):
            incident.move("PARTIALLY_RECOVERED")
        else:
            incident.move("FAILED_OR_ROLLED_BACK")
        self.ledger.append("repair_verified",
                           {"incident_id": incident.incident_id,
                            "state": incident.state}, verifier)
        return incident.state
