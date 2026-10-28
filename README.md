# Dream Team — re-scoped build (v0.1.0)

A coherent, honest, small Python implementation of the nine Master
Dev Team documents, built under the binding rules in RE-SCOPE.md:
authorized targets only, written scope, no autonomous engagements,
separation of powers, stub/mock backends only, no credentials
anywhere.

## Layout

```text
dreamteam/
  ledger.py       signed append-only ledger, Ed25519 checkpoints (OpenSSL CLI)
  errors.py       shared error types
  backends.py     Stub / Mock / DockerMiddleware (blocked) backends
  sandbox.py      MockSandbox with enforced isolation policy
  foundry.py      Doc 1 — model/agent evaluation with mock inference
  archive.py      Doc 2 — event contract, doctrine lifecycle, release gate
  anvil.py        Doc 3 — defensive adversarial evaluation (re-scoped)
  deploy.py       Doc 4 — Finished-Finished state machine, mock adapters
  repair.py       Doc 5 — RUNBOOK repair loop, R0-R3 approvals
  engine.py       Doc 6 — execution engine (re-scoped, no guessing/autonomy)
  toolchain.py    Doc 7 — native toolchain discovery, Toolbook, Sandbox Grid
  reverse.py      Doc 8 — source-first static analysis only (re-scoped)
  orchestrator.py Doc 9 — umbrella pipeline, Engineering Playbook
  cli.py          one smoke subcommand per module
tests/            unittest suite, including negative re-scope tests
```

## Run

```sh
python3 run_tests.py            # full suite (stdlib unittest, no deps)
python3 -m dreamteam.cli all smoke
```

No third-party packages are required. Signing uses the OpenSSL CLI,
the same approach as the Redbook anchor design. No network access,
no Docker, and no T340 middleware are needed to build or test: the
default backend is the stub, which honestly reports "blocked".

See RE-SCOPE.md for the binding rules and HONESTY-REPORT.md for
what is real, what is stub/mock, and what is blocked.
