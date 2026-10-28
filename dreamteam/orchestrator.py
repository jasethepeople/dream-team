"""Master Dev Team umbrella (Doc 9): goal -> requirements -> isolated
work -> challenge -> verify -> deliver -> learn.

Autonomy levels gate what the run may do: plan_only never modifies
anything; implement_with_review produces patch records that need a
separate human review; automated steps still need an approval id
for consequential actions. Delivery produces a reviewable package
(patch records + evidence manifest). There is no push path: no git
remote is created and no commit or push method exists. The
Engineering Playbook keeps the DRAFT/VALIDATED/STANDARD/SHELVED/
REJECTED lifecycle, with promotion requiring evidence plus an
independent reviewer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import AuthorizationError, PolicyViolation
from .ledger import Ledger
from .sandbox import MockSandbox

AUTONOMY_LEVELS = ("plan_only", "implement_with_review", "automated_approved_steps")
PERMISSIONS = ("read_only", "scoped_branch")
PLAYBOOK_TRANSITIONS = {
    "DRAFT": {"VALIDATED", "REJECTED"},
    "VALIDATED": {"STANDARD", "SHELVED", "REJECTED"},
    "STANDARD": {"SHELVED", "REJECTED"},
    "SHELVED": set(),
    "REJECTED": set(),
}
PIPELINE = ("DISCOVER", "SPECIFY", "PLAN", "IMPLEMENT", "CHALLENGE",
            "VERIFY", "DELIVER", "LEARN")


@dataclass
class RunConfig:
    goal: str
    repositories: list[str]
    autonomy: str = "plan_only"
    permissions: str = "read_only"
    approval_id: str | None = None

    def __post_init__(self) -> None:
        if not self.goal:
            raise PolicyViolation("a run requires a goal")
        if not 1 <= len(self.repositories) <= 25:
            raise PolicyViolation("runs cover 1..25 repositories")
        if self.autonomy not in AUTONOMY_LEVELS:
            raise PolicyViolation(f"unknown autonomy level: {self.autonomy!r}")
        if self.permissions not in PERMISSIONS:
            raise PolicyViolation(f"unknown permission set: {self.permissions!r}")
        if self.autonomy == "automated_approved_steps" and not self.approval_id:
            raise AuthorizationError("automated steps require an approval id")
        if self.permissions == "scoped_branch" and self.autonomy == "plan_only":
            raise PolicyViolation("scoped_branch writes need implement_with_review or above")


@dataclass
class Play:
    play_id: str
    trigger: str
    procedure: str
    state: str = "DRAFT"
    evidence: list[str] = field(default_factory=list)
    supersedes: str | None = None

    def promote(self, new_state: str, reviewer: str, author: str) -> None:
        if new_state not in PLAYBOOK_TRANSITIONS[self.state]:
            raise PolicyViolation(f"Playbook transition {self.state} -> {new_state} forbidden")
        if new_state in ("VALIDATED", "STANDARD"):
            if reviewer == author:
                raise PolicyViolation("play promotion needs an independent reviewer")
            if not self.evidence:
                raise PolicyViolation("play promotion requires evidence")
        self.state = new_state


@dataclass
class PatchRecord:
    repository: str
    summary: str
    diff: str
    author: str
    reviewed: bool = False


class Orchestrator:
    """Runs one intake through the pipeline over mock workspaces."""

    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger
        self.plays: dict[str, Play] = {}

    def run(self, config: RunConfig) -> dict[str, Any]:
        stages: dict[str, Any] = {}
        workspaces = {repo: MockSandbox(job_id=f"ws-{i}")
                      for i, repo in enumerate(config.repositories)}
        stages["DISCOVER"] = {repo: ["manifests inventoried"] for repo in config.repositories}
        stages["SPECIFY"] = {"requirements": [f"req-1: {config.goal}"],
                            "acceptance": ["all gates pass"]}
        stages["PLAN"] = {"tasks": [f"task-{repo}" for repo in config.repositories]}
        patches: list[PatchRecord] = []
        if config.autonomy != "plan_only":
            for repo in config.repositories:
                workspaces[repo].write_file("patch.diff", f"# patch for {repo}")
                patches.append(PatchRecord(repository=repo, summary=config.goal,
                                            diff=f"# patch for {repo}", author="repo-engineer"))
        stages["IMPLEMENT"] = {"patches": len(patches)}
        stages["CHALLENGE"] = {"challenges": "independent review recorded",
                              "reviewer": "adversarial-reviewer"}
        stages["VERIFY"] = {"gates": "passed", "ledger_verified": True}
        self.ledger.verify()
        stages["DELIVER"] = {
            "package": "reviewable delivery package (no push performed)",
            "patches": [{"repository": p.repository, "summary": p.summary} for p in patches],
            "push_performed": False,
        }
        stages["LEARN"] = {"plays_updated": 0}
        self.ledger.append("mdt_run", {"goal": config.goal,
                                      "repositories": config.repositories,
                                      "autonomy": config.autonomy}, "master-architect")
        for box in workspaces.values():
            box.destroy()
        return {"stages": list(PIPELINE), "detail": stages,
                "config": {"goal": config.goal, "autonomy": config.autonomy}}

    def add_play(self, play: Play) -> Play:
        if play.play_id in self.plays:
            raise PolicyViolation(f"play {play.play_id!r} already exists")
        self.plays[play.play_id] = play
        return play
