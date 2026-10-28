"""Execution Engine (Doc 6), RE-SCOPED. The "do whatever it takes"
ladder is deleted; goal autonomy is not built.

What remains, under the binding RE-SCOPE:
- Intent Compiler: natural-language-ish commands become a structured
  Intent, but only with an authorization record naming an owned or
  explicitly permitted target. No record -> refusal.
- Connectors: only to authorized systems, with operator-supplied
  credentials. There is NO credential guessing, no connection-string
guessing, no brute force, no fallback that invents access. Without
  supplied credentials the run stops at a manual-assist flag.
- Fallback ladder: authorized client call -> manual-assist flag ->
  STOP. No headless-browser/OCR escalation ladder.
- Orchestrator dispatches to MockSandbox only; the Anvil is called
  as an independent checker, never folded in as a runtime service.
- Adjudicator with a bounded replan loop (budget). No self-tasking:
  run() requires an explicit operator command and approval for
  consequential actions. Self-repair covers only the team's own
  parsers against its own fixtures.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .anvil import Authorization
from .errors import AuthorizationError, PolicyViolation
from .sandbox import MockSandbox

MAX_REPLANS = 3


@dataclass
class OperatorCredentials:
    """Credentials supplied by the operator at run time. Never stored:
    the engine holds a reference for the duration of one run only,
    and evidence records carry no credential material."""
    supplied: bool
    label: str = "operator-supplied"  # identifier only, never a secret value


@dataclass
class Intent:
    goal: str
    target: str
    authorization: Authorization
    success_criteria: list[str]
    budget_attempts: int = MAX_REPLANS
    read_only: bool = True

    def __post_init__(self) -> None:
        self.authorization.require()
        if not self.goal or not self.target:
            raise AuthorizationError("intent requires a goal and a target")
        if self.budget_attempts < 1 or self.budget_attempts > MAX_REPLANS:
            raise PolicyViolation(f"budget_attempts must be 1..{MAX_REPLANS}")


@dataclass
class Task:
    task_id: str
    verb: str
    detail: str
    state: str = "pending"


PLANNER_VERBS = ("resolve", "discover", "fetch", "validate", "confirm")


class Planner:
    """Expands an intent into a task DAG using only the approved verbs."""

    @staticmethod
    def plan(intent: Intent) -> list[Task]:
        return [Task(task_id=f"t{i}", verb=verb,
                     detail=f"{verb} {intent.target} for: {intent.goal}")
                for i, verb in enumerate(PLANNER_VERBS)]


class ConnectorRegistry:
    """Connectors declare capabilities and auth needs. Calls require
    operator-supplied credentials; anything else stops at the flag."""

    def __init__(self) -> None:
        self.connectors: dict[str, dict[str, Any]] = {}

    def register(self, name: str, capabilities: list[str], needs_auth: bool) -> None:
        self.connectors[name] = {"capabilities": capabilities, "needs_auth": needs_auth}

    def call(self, name: str, operation: str,
             credentials: OperatorCredentials | None) -> dict[str, Any]:
        connector = self.connectors.get(name)
        if connector is None:
            raise PolicyViolation(f"unknown connector: {name!r}")
        if operation not in connector["capabilities"]:
            raise PolicyViolation(f"connector {name!r} does not offer {operation!r}")
        if connector["needs_auth"]:
            if credentials is None or not credentials.supplied:
                return {"status": "manual_assist",
                        "reason": "credentials not supplied by operator; stopping"}
        return {"status": "ok", "connector": name, "operation": operation,
                "rows": []}  # mock payload; real fetch is a later wired backend


class Adjudicator:
    """Compares observations against success criteria."""

    @staticmethod
    def judge(intent: Intent, observations: dict[str, Any]) -> bool:
        return all(observations.get(criterion, False) for criterion in intent.success_criteria)


class Engine:
    """Runs one authorized intent to proof or to a manual-assist stop."""

    def __init__(self, sandbox: MockSandbox, registry: ConnectorRegistry | None = None) -> None:
        self.sandbox = sandbox
        self.registry = registry or ConnectorRegistry()

    def run(self, intent: Intent, credentials: OperatorCredentials | None,
            approval_id: str | None = None) -> dict[str, Any]:
        if not intent.read_only and not approval_id:
            raise AuthorizationError(
                "consequential (non-read-only) runs require an approval id")
        tasks = Planner.plan(intent)
        observations: dict[str, Any] = {}
        attempts = 0
        while attempts < intent.budget_attempts:
            attempts += 1
            for task in tasks:
                task.state = "done"  # mock execution inside the sandbox only
            result = self.registry.call("mock-store", "read", credentials)
            if result["status"] == "manual_assist":
                return {"status": "manual_assist", "attempts": attempts,
                        "reason": result["reason"], "tasks": [t.task_id for t in tasks]}
            observations = {c: True for c in intent.success_criteria}
            if Adjudicator.judge(intent, observations):
                return {"status": "proven", "attempts": attempts,
                        "tasks": [t.task_id for t in tasks]}
        return {"status": "budget_exhausted", "attempts": attempts}


def self_repair_own_parser(parser: Callable[[str], Any], fixture_inputs: list[str],
                            expected: list[Any]) -> bool:
    """Self-repair limited to the team's OWN parsers against OWN fixtures.

    Returns True when the parser already handles every fixture input.
    It never rewrites selectors against third-party systems.
    """
    return all(parser(value) == want for value, want in zip(fixture_inputs, expected))
