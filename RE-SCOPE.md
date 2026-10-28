# RE-SCOPE — Dream Team build, binding rules

Date: 2026-10-27. Ruled by Jason: the nine source documents are built
under proper cybersecurity terms. Where a source document conflicts
with this file, this file wins. The original documents are untouched
source material; they are not copied into this project.

## General rules (apply to every module)

1. **Authorized targets only.** Every capability operates only against:
   (a) software and repositories the operator owns or has explicit
   written permission to examine, (b) mock/fixture targets the team
   itself creates, or (c) the team's own sandboxes. No live targets.
   No third-party targets. Ever.
2. **Written scope.** Every engagement, intake, intent, and deployment
   carries an authorization record (who authorized, what target, what
   is permitted, expiry) before any work starts. No record, no work.
3. **No autonomous engagements.** No agent spins up work on its own.
   Every consequential action needs explicit human approval recorded
   before it runs. There is no self-tasking layer.
4. **Separation of powers.** The role that finds a defect never
   certifies its own fix. Finder, fixer, verifier, and approver are
   distinct actors, enforced in code (actor identity checks).
5. **Stub/mock backends only.** No untrusted code executes on any
   host. The T340 Docker middleware is BLOCKED until its isolation,
   allowlist, and token handling are independently verified. Backends
   report "blocked" rather than pretend to execute.
6. **No credentials in the system.** Credentials are supplied by the
   operator at run time, never stored, never logged, never guessed,
   never written into evidence. Evidence holds digests and
   identifiers only.

## What was removed or narrowed, with the source wording

### Anvil (Doc 3, Adversarial / Security)

Source phrase removed: "controlled sandbox-escape tests" and
"Run attacks against mock targets and mock sandboxes in tests, with
real sandboxed attacks wired later via the T340 middleware."

Re-scoped to: defensive adversarial evaluation only. Boundary checks
are simulated fixtures that assert the MockSandbox DENIES an
attempt (read outside the workspace, cross-job access, network
attempt). No real escape technique is implemented, attempted, or
catalogued. No exploit-reproduction pipeline against real software.

Source phrase removed: "researches legitimate system capabilities
and their abuse potential" (Doc 3 section 12, describing the LotL
team). No abuse-potential research catalog is built.

Source constraint retained and strengthened: "Do not attack live
targets, do not run untrusted attack code directly on this host, and
do not blast unpatched details." Stop-work conditions retained:
any real escape, credential exposure, or unexpected egress stops
the job and is recorded.

Retained as specified: SAST-style static checks against the team's
own code, dependency/pin checks, secret-pattern scanning of the
team's own artifacts, fuzz-style malformed-input tests against the
team's own validators, finding lifecycle, severity gates, and the
independent adjudicator.

### Master Reverse (Doc 8)

Source boundary retained verbatim in spirit: "analysis should be
limited to software you own or have permission to examine, with
safeguards against extracting secrets, bypassing licensing or
access controls, or repurposing findings to compromise third-party
systems."

Re-scoped to: source-first static analysis only. The intake records
authorization and a SHA-256 of the inputs before analysis. Python
source is inventoried with AST parsing (modules, functions,
imports, call edges). Compiled binaries, firmware images, and
opaque executables are REFUSED at intake (unsupported target),
not analyzed. No disassembly tooling, no firmware extraction
tooling, no secret extraction, no licensing/access-control bypass,
no protection defeat. No dynamic execution of target code on any
host: analysis never executes the target.

### Execution Engine (Doc 6)

Source phrase removed entirely: "Making 'do whatever it takes'
actually work" / "It's what makes 'do whatever it takes' mean
something." The persistence drive loop is not built.

Source phrase removed entirely: "connection string guessing" as a
fallback step ("native client -> connection string guessing ->
schema introspection -> row sampling"). There is no credential
guessing of any kind. Connectors accept only operator-supplied
credentials; without them the run stops at a manual-assist flag.

Source fallback ladder replaced. The old ladder ("API -> raw HTTP
-> headless browser -> rendered DOM -> OCR -> manual-assist flag")
is replaced with: authorized API/client call with supplied
credentials -> manual-assist flag -> STOP. No scraping in
violation of terms or robots rules. No bulk extraction from
third-party systems.

Source phrase removed: "Goal autonomy - an agent deciding to spin
up whole engagements on its own - is a later layer." Goal autonomy
is OUT. It is not built, not stubbed, not planned. There is no code
path that creates engagements without an explicit operator command
plus an authorization record.

Source repurposing removed: "the Anvil spec *is* the control plane
for these agents" / Anvil roles "become the runtime services."
The Anvil's roles are NOT runtime services. Attacker, verifier, and
approver stay separate; the engine calls the Anvil only as an
independent checker, never as a folded-in service.

Source self-repair narrowed: "spawn a repair sub-agent that diffs
the failure, rewrites the selector/parser, and retests" is limited
to the team's OWN parsers/selectors against its OWN fixtures.
No self-repair against third-party systems.

Retained as specified: Intent Compiler (structured intent with
success criteria and budget), Planner (task DAG), Orchestrator
(dispatch to MockSandbox only), Adjudicator Gate with a bounded
replan loop, connector registry, schema validation, idempotent
content-addressed collection from authorized systems only.

### Backends (all docs, execution-stub appendices)

Source backend rule retained: stub default, mock for tests,
"returns execution blocked if no real backend is configured",
"does NOT run untrusted repository code directly on this host."

Re-scoped: the DockerMiddleware module exists as a typed,
request-validating module, but its run path is BLOCKED unless an
operator explicitly sets the verified flag after independent
verification of the T340 middleware AND supplies a token at run
time via environment. No token is stored anywhere in this project.
Until then every backend job reports blocked, honestly.

## What this build is

A coherent, honest, small Python implementation of the nine
modules under the rules above: shared signed ledger, stub/mock
backends, MockSandbox isolation, per-module state machines, role
separation enforced in code, and tests — including negative tests
proving the re-scope holds. See HONESTY-REPORT.md for what is
real, what is stub, and what is blocked.
