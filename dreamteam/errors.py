"""Shared error types for the Dream Team package."""
from __future__ import annotations


class DreamTeamError(Exception):
    """Base class for all Dream Team errors."""


class AuthorizationError(DreamTeamError):
    """Raised when a required authorization record is missing or invalid."""


class BlockedError(DreamTeamError):
    """Raised when an operation is blocked (no backend, unverified middleware)."""


class PolicyViolation(DreamTeamError):
    """Raised when an action violates an enforced policy (sandbox, gate)."""


class UnsupportedTarget(DreamTeamError):
    """Raised when a target type is outside the re-scoped build (e.g. binaries)."""
