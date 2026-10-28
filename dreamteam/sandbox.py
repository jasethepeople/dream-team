"""MockSandbox: an in-memory isolated workspace with enforced policy.

The sandbox is a simulation used for tests and fixtures. It enforces:
- reads/writes only inside the job's own workspace;
- no access to another job's files, host paths, or credential files;
- no network access (default deny; allowlist is empty unless the
  operator explicitly supplies approved destinations);
- quotas on file count and total bytes.

Violations raise PolicyViolation and are recorded in the denial log.
A fixture "attack" is therefore an assertion that the sandbox DENIES
the attempt; no real escape technique exists here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .errors import PolicyViolation

MAX_FILES = 100
MAX_BYTES = 1_000_000
SENSITIVE_NAMES = ("id_rsa", "id_ed25519", ".pem", "credentials", "token", ".env")


@dataclass
class Denial:
    action: str
    path: str
    reason: str


class MockSandbox:
    """In-memory sandbox for one job."""

    def __init__(self, job_id: str, network_allowlist: tuple[str, ...] = ()) -> None:
        if not job_id:
            raise PolicyViolation("job_id is required")
        self.job_id = job_id
        self.files: dict[str, bytes] = {}
        self.denials: list[Denial] = []
        self.network_allowlist = tuple(network_allowlist)
        self.destroyed = False

    # -- policy --
    def _check_alive(self) -> None:
        if self.destroyed:
            raise PolicyViolation("sandbox has been destroyed (clean teardown)")

    def _check_path(self, action: str, path: str) -> str:
        self._check_alive()
        normalized = path.replace("\\", "/").strip()
        if normalized.startswith("/") or ".." in normalized.split("/"):
            self.denials.append(Denial(action, path, "absolute or parent path"))
            raise PolicyViolation(f"{action} denied: path escapes workspace: {path!r}")
        if normalized.startswith("other-job/") or "/other-job/" in normalized:
            self.denials.append(Denial(action, path, "cross-job access"))
            raise PolicyViolation(f"{action} denied: cross-job access: {path!r}")
        lowered = normalized.lower()
        if any(name in lowered for name in SENSITIVE_NAMES):
            self.denials.append(Denial(action, path, "sensitive filename"))
            raise PolicyViolation(f"{action} denied: sensitive filename: {path!r}")
        return normalized

    # -- filesystem --
    def write_file(self, path: str, content: bytes | str) -> None:
        normalized = self._check_path("write", path)
        data = content.encode("utf-8") if isinstance(content, str) else content
        if normalized not in self.files and len(self.files) >= MAX_FILES:
            raise PolicyViolation("file quota exceeded")
        if sum(len(v) for v in self.files.values()) + len(data) > MAX_BYTES:
            raise PolicyViolation("byte quota exceeded")
        self.files[normalized] = data

    def read_file(self, path: str) -> bytes:
        normalized = self._check_path("read", path)
        if normalized not in self.files:
            raise PolicyViolation(f"read denied: no such file in workspace: {path!r}")
        return self.files[normalized]

    def list_files(self) -> list[str]:
        self._check_alive()
        return sorted(self.files)

    # -- network --
    def network_fetch(self, destination: str) -> bytes:
        self._check_alive()
        if destination not in self.network_allowlist:
            self.denials.append(Denial("network", destination, "default-deny egress"))
            raise PolicyViolation(f"network denied: {destination!r} not on allowlist")
        return b""  # allowlisted destinations return empty mock payloads

    def destroy(self) -> None:
        """Clean teardown: files are dropped, denials retained for audit."""
        self.files.clear()
        self.destroyed = True
