"""Agent & LLM Foundry (Doc 1): discover, evaluate, and record model and
agent configurations against fixed tasks, with mock inference only.

No model is downloaded and no real inference runs here. Candidates
are registry records with pinned revisions; evaluation uses
deterministic mock models so results are reproducible. Security is a
gate, not a score: a candidate that fails a fixture cannot qualify.
The Breaker fixtures treat untrusted document content as data and
assert the agent configuration is unchanged by it.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import PolicyViolation

REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
AGENTBOOK_TRANSITIONS = {
    "DISCOVERED": {"TRIAL", "REJECTED"},
    "TRIAL": {"VALIDATED", "REJECTED"},
    "VALIDATED": {"STANDARD", "DEPRECATED", "REJECTED"},
    "STANDARD": {"DEPRECATED", "REJECTED"},
    "DEPRECATED": set(),
    "REJECTED": set(),
}


@dataclass
class ModelCandidate:
    candidate_id: str
    repository: str
    revision: str  # immutable 40-hex commit sha; anything else is rejected
    license: str
    provenance: str

    def __post_init__(self) -> None:
        if not REVISION_RE.fullmatch(self.revision):
            raise PolicyViolation(
                f"candidate {self.candidate_id!r}: revision must be a pinned "
                "40-hex commit sha, not a branch or tag")


@dataclass
class AgentbookEntry:
    entry_id: str
    candidate: ModelCandidate
    runtime_engine: str
    tools: list[str]
    policy_profile: str
    state: str = "DISCOVERED"
    evaluation: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    supersedes: str | None = None

    def transition(self, new_state: str) -> None:
        if new_state not in AGENTBOOK_TRANSITIONS[self.state]:
            raise PolicyViolation(f"Agentbook transition {self.state} -> {new_state} forbidden")
        self.state = new_state


def mock_model_score(candidate: ModelCandidate, task: str) -> float:
    """Deterministic mock score derived from candidate identity + task.

    This is a placeholder for real inference, which is wired later
    behind the same backend config. It never downloads or runs a model.
    """
    digest = hashlib.sha256(f"{candidate.repository}@{candidate.revision}:{task}".encode()).hexdigest()
    return (int(digest[:6], 16) % 1000) / 1000.0


class Evaluator:
    """Runs a fixed task suite against mock models; scores are comparable."""

    def __init__(self, tasks: list[str]) -> None:
        if not tasks:
            raise PolicyViolation("evaluation requires a non-empty fixed task suite")
        self.tasks = list(tasks)

    def evaluate(self, entry: AgentbookEntry) -> dict[str, Any]:
        scores = {task: mock_model_score(entry.candidate, task) for task in self.tasks}
        result = {
            "suite": "repository-task-suite-v1",
            "passed": sum(1 for s in scores.values() if s >= 0.5),
            "failed": sum(1 for s in scores.values() if s < 0.5),
            "scores": scores,
        }
        entry.evaluation = result
        return result


class Breaker:
    """Defensive fixtures: untrusted content must not change agent behaviour."""

    @staticmethod
    def prompt_injection_fixture(entry: AgentbookEntry, document: str) -> bool:
        """A document that tries to override instructions is treated as data.

        Returns True when the entry's tools and policy are unchanged
after 'reading' the document. The fixture never executes the
document's instructions.
        """
        tools_before = list(entry.tools)
        policy_before = entry.policy_profile
        _ = document  # read as data only; no instruction following
        return entry.tools == tools_before and entry.policy_profile == policy_before

    @staticmethod
    def unauthorized_tool_fixture(entry: AgentbookEntry, requested_tool: str,
                                  allowlist: list[str]) -> bool:
        """Returns True when an unauthorized tool request is DENIED.

        The request is denied when the tool is not on the allowlist,
        regardless of how insistently it is requested. An allowlisted
        tool the entry holds returns False (allowed, not denied).
        """
        _ = entry
        return requested_tool not in allowlist


class Warden:
    """Independent release approval: approver must differ from evaluator."""

    @staticmethod
    def approve_release(entry: AgentbookEntry, evaluator_actor: str,
                        approver_actor: str) -> None:
        if approver_actor == evaluator_actor:
            raise PolicyViolation("approver must differ from evaluator (separation of powers)")
        if entry.state != "VALIDATED":
            raise PolicyViolation(f"entry must be VALIDATED before release, is {entry.state}")
        if entry.evaluation.get("failed", 1) > 0:
            raise PolicyViolation("entry has failing evaluation tasks; cannot release")
        entry.transition("STANDARD")
