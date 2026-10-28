"""Master Reverse (Doc 8), RE-SCOPED: source-first static analysis only.

- Intake requires an authorization record AND a SHA-256 hash of the
  inputs, recorded before analysis.
- Only owned/authorized Python source is analyzed, with the AST
  module (inventory of modules, functions, classes, imports, and
  call edges). Analysis NEVER executes target code.
- Compiled binaries, firmware images, and opaque executables are
  REFUSED at intake (UnsupportedTarget). No disassembly, no
  firmware extraction, no secret extraction, no licensing or
  access-control bypass, no protection defeat.
- Reversebook claims carry evidence links, counter-hypotheses, and
  confidence states; the verifier is a different actor from the
  analyst.
"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .anvil import Authorization
from .errors import AuthorizationError, PolicyViolation, UnsupportedTarget

REVERSEBOOK_TRANSITIONS = {
    "HYPOTHESIS": {"SUPPORTED", "DISPROVED"},
    "SUPPORTED": {"REPRODUCED", "DISPROVED", "SUPERSEDED"},
    "REPRODUCED": {"STANDARD", "DISPROVED", "SUPERSEDED"},
    "STANDARD": {"SUPERSEDED", "DISPROVED"},
    "SUPERSEDED": set(),
    "DISPROVED": set(),
}
BINARY_EXTENSIONS = {".exe", ".dll", ".so", ".dylib", ".bin", ".fw", ".hex", ".elf", ".o", ".a"}
BINARY_MAGICS = (b"\x7fELF", b"MZ", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class Intake:
    intake_id: str
    target_dir: Path
    authorization: Authorization
    input_hashes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.authorization.require()
        if not self.target_dir.is_dir():
            raise AuthorizationError(f"target is not a directory: {self.target_dir}")
        for path in sorted(self.target_dir.rglob("*")):
            if path.is_file():
                if path.suffix.lower() in BINARY_EXTENSIONS:
                    raise UnsupportedTarget(
                        f"binary/firmware target refused: {path.name} "
                        "(source-first analysis only)")
                head = path.read_bytes()[:4]
                if head in BINARY_MAGICS:
                    raise UnsupportedTarget(
                        f"binary target refused by magic bytes: {path.name}")
                self.input_hashes[str(path.relative_to(self.target_dir))] = sha256_file(path)


@dataclass
class ReversebookClaim:
    claim_id: str
    claim: str
    state: str = "HYPOTHESIS"
    evidence: list[str] = field(default_factory=list)
    counter_hypothesis: str = ""
    analyst: str = ""
    verifier: str = ""

    def transition(self, new_state: str, actor: str) -> None:
        if new_state not in REVERSEBOOK_TRANSITIONS[self.state]:
            raise PolicyViolation(f"Reversebook transition {self.state} -> {new_state} forbidden")
        if new_state in ("REPRODUCED", "STANDARD") and actor == self.analyst:
            raise PolicyViolation("analyst cannot verify their own claim")
        if new_state in ("REPRODUCED", "STANDARD"):
            self.verifier = actor
        self.state = new_state


class StaticAnalyzer:
    """AST-based inventory of owned Python source. No execution."""

    @staticmethod
    def analyze(intake: Intake) -> dict[str, Any]:
        modules: list[dict[str, Any]] = []
        for rel, _digest in sorted(intake.input_hashes.items()):
            path = intake.target_dir / rel
            if path.suffix != ".py":
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
            functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
            classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
            calls = [n.func.id for n in ast.walk(tree)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
            modules.append({"file": rel, "functions": functions, "classes": classes,
                            "imports": sorted(set(imports)), "calls": sorted(set(calls))})
        return {"intake_id": intake.intake_id, "modules": modules,
                "input_hashes": intake.input_hashes}
