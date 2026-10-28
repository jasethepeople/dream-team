"""Deployment / Finished-Finished Team (Doc 4): the Last Mile.

Seven-stage lifecycle with an explicit state machine; ACCEPTED is
the only finished state. Provider adapters are mock implementations
plus a blocked T340 adapter: no real credentials exist anywhere in
this build, and no real deployment is performed. Acceptance probes
run against mock endpoints; retries are recorded and never erase
the original failure. Every outcome is written to the ledger.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import BlockedError, PolicyViolation
from .ledger import Ledger

STATES = ("PREPARED", "DEPLOYING", "DEPLOYED_UNVERIFIED", "VERIFYING",
          "ACCEPTED", "ROLLED_BACK", "FAILED_UNRECOVERED")
TRANSITIONS = {
    "PREPARED": {"DEPLOYING"},
    "DEPLOYING": {"DEPLOYED_UNVERIFIED", "FAILED_UNRECOVERED"},
    "DEPLOYED_UNVERIFIED": {"VERIFYING", "ROLLED_BACK"},
    "VERIFYING": {"ACCEPTED", "ROLLED_BACK", "FAILED_UNRECOVERED"},
    "ACCEPTED": set(),
    "ROLLED_BACK": set(),
    "FAILED_UNRECOVERED": set(),
}


@dataclass
class Release:
    release_id: str
    artifact_digest: str
    commit: str
    environment: str
    adapter_id: str


class DeploymentAdapter:
    """Provider adapter contract (interface sketch made real for mocks)."""

    adapter_id = "base"

    def preflight(self, release: Release) -> dict[str, Any]:
        raise NotImplementedError

    def deploy(self, release: Release) -> str:
        raise NotImplementedError

    def get_deployment_status(self, deployment_id: str) -> str:
        raise NotImplementedError

    def run_health_checks(self, deployment_id: str) -> dict[str, str]:
        raise NotImplementedError

    def collect_metrics(self, deployment_id: str) -> dict[str, float]:
        raise NotImplementedError

    def rollback(self, deployment_id: str, previous_release: Release) -> str:
        raise NotImplementedError

    def verify_rollback(self, previous_release: Release) -> bool:
        raise NotImplementedError


class MockDeployAdapter(DeploymentAdapter):
    """Mock provider: deployments and probes are in-memory fixtures."""

    adapter_id = "mock"

    def __init__(self, healthy: bool = True, journeys: dict[str, bool] | None = None) -> None:
        self.healthy = healthy
        self.journeys = journeys or {"home": True, "login": True}
        self.deployments: dict[str, Release] = {}
        self.counter = 0

    def preflight(self, release: Release) -> dict[str, Any]:
        return {"artifact": release.artifact_digest, "environment": release.environment,
                "rollback_ready": True}

    def deploy(self, release: Release) -> str:
        self.counter += 1
        deployment_id = f"mock-deploy-{self.counter}"
        self.deployments[deployment_id] = release
        return deployment_id

    def get_deployment_status(self, deployment_id: str) -> str:
        return "running" if deployment_id in self.deployments else "unknown"

    def run_health_checks(self, deployment_id: str) -> dict[str, str]:
        ok = self.healthy and deployment_id in self.deployments
        return {"health": "passed" if ok else "failed"}

    def collect_metrics(self, deployment_id: str) -> dict[str, float]:
        return {"latency_p95_ms": 120.0 if self.healthy else 9000.0,
                "error_rate": 0.0 if self.healthy else 0.85}

    def rollback(self, deployment_id: str, previous_release: Release) -> str:
        self.deployments.pop(deployment_id, None)
        return f"mock-rollback-to-{previous_release.release_id}"

    def verify_rollback(self, previous_release: Release) -> bool:
        return True


class T340DeployAdapter(DeploymentAdapter):
    """T340 adapter: BLOCKED. No credentials, no access mechanism confirmed."""

    adapter_id = "t340"

    def _blocked(self) -> BlockedError:
        return BlockedError("T340 deployment blocked: access mechanism and runtime "
                            "unconfirmed; no credentials configured")

    def preflight(self, release: Release) -> dict[str, Any]:
        raise self._blocked()

    def deploy(self, release: Release) -> str:
        raise self._blocked()


class Deployment:
    """One release moving through the Finished-Finished state machine."""

    def __init__(self, release: Release, adapter: DeploymentAdapter, ledger: Ledger) -> None:
        self.release = release
        self.adapter = adapter
        self.ledger = ledger
        self.state = "PREPARED"
        self.deployment_id: str | None = None
        self.attempts: list[dict[str, Any]] = []

    def _move(self, new_state: str) -> None:
        if new_state not in TRANSITIONS[self.state]:
            raise PolicyViolation(f"deployment transition {self.state} -> {new_state} forbidden")
        self.state = new_state
        self.ledger.append("deployment_state", {"release_id": self.release.release_id,
                                                "state": new_state}, "deploy-lead")

    def run(self) -> str:
        self.adapter.preflight(self.release)
        self._move("DEPLOYING")
        self.deployment_id = self.adapter.deploy(self.release)
        self._move("DEPLOYED_UNVERIFIED")
        self._move("VERIFYING")
        checks = self.adapter.run_health_checks(self.deployment_id)
        metrics = self.adapter.collect_metrics(self.deployment_id)
        self.attempts.append({"checks": checks, "metrics": metrics})
        if checks.get("health") == "passed" and metrics.get("error_rate", 1.0) < 0.05:
            self._move("ACCEPTED")
        else:
            self._move("ROLLED_BACK")
        return self.state

    def rollback_to(self, previous_release: Release) -> bool:
        if self.state not in ("VERIFYING", "DEPLOYED_UNVERIFIED"):
            raise PolicyViolation(f"rollback not allowed from {self.state}")
        if self.deployment_id is None:
            raise PolicyViolation("no deployment to roll back")
        self.adapter.rollback(self.deployment_id, previous_release)
        ok = self.adapter.verify_rollback(previous_release)
        if ok:
            self._move("ROLLED_BACK")
        return ok
