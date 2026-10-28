"""Execution backends: stub default, mock for tests, T340 middleware BLOCKED.

Every backend exposes run/status/stop. The StubBackend reports
"blocked" when no real backend is configured and never executes
anything. The DockerMiddlewareBackend validates job requests
(allowlisted images, argv arrays, timeout bounds) but its run path
stays blocked until an operator sets DREAMTEAM_T340_VERIFIED=1
after independent verification of the middleware AND supplies a
token at run time via DREAMTEAM_T340_TOKEN. No token is ever
stored in this project. Until both conditions hold, run() returns
a blocked result and performs no network call.
"""
from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import BlockedError

ALLOWED_IMAGES = frozenset({"python:3.12-slim", "node:22-slim", "rust:1.82-slim"})
DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 300


@dataclass
class JobResult:
    job_id: str
    status: str  # "blocked" | "completed" | "failed"
    output: str = ""
    blocked_reason: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


class Backend:
    """Interface for an execution backend: run, status, stop."""

    name = "base"

    def run(self, job: dict[str, Any]) -> JobResult:
        raise NotImplementedError

    def status(self, job_id: str) -> JobResult:
        raise NotImplementedError

    def stop(self, job_id: str) -> JobResult:
        raise NotImplementedError


def validate_job(job: dict[str, Any]) -> dict[str, Any]:
    """Validate a middleware job request. Raises ValueError on violation."""
    if job.get("image") not in ALLOWED_IMAGES:
        raise ValueError(f"image not on allowlist: {job.get('image')!r}")
    argv = job.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        raise ValueError("argv must be a non-empty list of strings (no shell strings)")
    timeout = job.get("timeout", DEFAULT_TIMEOUT)
    if not isinstance(timeout, int) or timeout < 1 or timeout > MAX_TIMEOUT:
        raise ValueError(f"timeout must be 1..{MAX_TIMEOUT}")
    network = job.get("network_policy", "none")
    if network != "none":
        raise ValueError("network_policy must be 'none' unless explicitly approved")
    if job.get("privileged") or job.get("host_mounts") or job.get("volumes"):
        raise ValueError("privileged, host mounts, and volumes are forbidden")
    return {"image": job["image"], "argv": argv, "timeout": timeout,
            "network_policy": network}


class StubBackend(Backend):
    """Default backend: reports blocked, executes nothing."""

    name = "stub"

    def run(self, job: dict[str, Any]) -> JobResult:
        return JobResult(job_id=job.get("job_id", "stub-0"), status="blocked",
                         blocked_reason="no real backend configured (BACKEND=stub)")

    def status(self, job_id: str) -> JobResult:
        return JobResult(job_id=job_id, status="blocked",
                         blocked_reason="no real backend configured (BACKEND=stub)")

    def stop(self, job_id: str) -> JobResult:
        return JobResult(job_id=job_id, status="blocked",
                         blocked_reason="no real backend configured (BACKEND=stub)")


class MockBackend(Backend):
    """Test backend: runs only pre-registered Python callables, no shell."""

    name = "mock"

    def __init__(self, handlers: dict[str, Callable[[dict[str, Any]], str]] | None = None) -> None:
        self.handlers = dict(handlers or {})
        self.jobs: dict[str, JobResult] = {}

    def register(self, name: str, handler: Callable[[dict[str, Any]], str]) -> None:
        self.handlers[name] = handler

    def run(self, job: dict[str, Any]) -> JobResult:
        validated = validate_job(job)
        handler = self.handlers.get(validated["argv"][0])
        if handler is None:
            result = JobResult(job_id=job.get("job_id", "mock-0"), status="failed",
                               output=f"no mock handler for {validated['argv'][0]!r}")
        else:
            try:
                result = JobResult(job_id=job.get("job_id", "mock-0"),
                                   status="completed", output=handler(job))
            except Exception as exc:  # mock handlers fail closed
                result = JobResult(job_id=job.get("job_id", "mock-0"),
                                   status="failed", output=f"mock handler error: {exc}")
        self.jobs[result.job_id] = result
        return result

    def status(self, job_id: str) -> JobResult:
        return self.jobs.get(job_id, JobResult(job_id=job_id, status="failed",
                                              output="unknown job"))

    def stop(self, job_id: str) -> JobResult:
        result = JobResult(job_id=job_id, status="failed", output="stopped")
        self.jobs[job_id] = result
        return result


class DockerMiddlewareBackend(Backend):
    """T340 Docker middleware client. BLOCKED until independently verified.

    The request shape is implemented and validated; the network call
    is gated behind DREAMTEAM_T340_VERIFIED=1 plus a run-time token.
    Default behaviour: blocked, no network traffic.
    """

    name = "t340-middleware"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or os.environ.get("DREAMTEAM_T340_URL", "")

    def _verified(self) -> bool:
        return os.environ.get("DREAMTEAM_T340_VERIFIED") == "1" and bool(self.base_url)

    def run(self, job: dict[str, Any]) -> JobResult:
        validated = validate_job(job)
        job_id = job.get("job_id", "t340-0")
        if not self._verified():
            return JobResult(
                job_id=job_id, status="blocked",
                blocked_reason=("T340 middleware blocked: isolation, allowlist, and "
                                "token handling not yet independently verified"))
        token = os.environ.get("DREAMTEAM_T340_TOKEN", "")
        if not token:
            return JobResult(job_id=job_id, status="blocked",
                             blocked_reason="T340 middleware token not supplied at run time")
        try:
            request = urllib.request.Request(
                self.base_url.rstrip("/") + "/job",
                data=__import__("json").dumps(validated).encode("utf-8"),
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
                body = response.read().decode("utf-8", "replace")
            return JobResult(job_id=job_id, status="completed", output=body)
        except Exception as exc:
            return JobResult(job_id=job_id, status="failed", output=f"middleware error: {exc}")

    def status(self, job_id: str) -> JobResult:
        return JobResult(job_id=job_id, status="blocked",
                         blocked_reason="T340 middleware blocked pending verification")

    def stop(self, job_id: str) -> JobResult:
        return JobResult(job_id=job_id, status="blocked",
                         blocked_reason="T340 middleware blocked pending verification")


def backend_from_env() -> Backend:
    """Wire backend by env var. Default is the stub (blocked)."""
    name = os.environ.get("BACKEND", "stub")
    if name == "t340-middleware":
        return DockerMiddlewareBackend()
    if name == "mock":
        return MockBackend()
    if name == "stub":
        return StubBackend()
    raise BlockedError(f"unknown backend {name!r}; refusing to guess")
