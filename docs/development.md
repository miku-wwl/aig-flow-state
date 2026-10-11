# Development and reproduction

Python is constrained to 3.13. `uv.lock` pins the Git release commit and transitive
dependencies. The runtime must be installed normally; no `PYTHONPATH`/editable core
checkout is used. The consumer itself can be editable during development.

```powershell
uv sync --locked
uv run python -c "import sys, importlib.metadata as m; print(sys.version); print(m.version('agentic-intent-gate')); print(m.distribution('agentic-intent-gate').read_text('direct_url.json'))"
uv run pytest -q
uv run ruff check
uv run ruff format --check
uv lock --check
```

The pytest hook creates the ignored artifact parent. Generated test state is beneath
`.artifacts/test-state`; pytest replaces its own disposable test directory on each run.
Screenshots and evidence live in separate `.artifacts/screenshots` and `.artifacts/evidence`
directories. Do not put manually retained data in disposable test-state directories.
Browser regression uses headless installed Chrome; the separate live check opens a
headed Chrome browser. Tests start a real uvicorn subprocess and stop it through a
test-only stdin channel that sets `server.should_exit`, allowing full lifespan shutdown.
Normal product startup is `safeops serve` with foreground Ctrl+C shutdown.

## HTTP routes

All private routes require the private file's value in the `Authorization: Bearer ...`
header. The UI file picker reads it into memory. Never paste it into terminal commands,
URLs, source, CI logs, .env files, screenshots or browser storage. Origins must match
the loopback service. No mutation is replayed when a browser refresh restores a Run.

| Method and path | Contract and owner |
| --- | --- |
| `GET /api/health` | Consumer public health |
| `GET /api/status` | Consumer mode/model/safe error/scope status, no secrets |
| `POST /api/plans` | Core preview; body `{text}`; no persistent Run |
| `POST /api/runs` | Core generation and persisted Run; body `{text}` |
| `GET /api/runs/{uuid}` | Core Run snapshot |
| `POST /api/runs/{uuid}/approval` | Core `{decision: APPROVE or REJECT, expected_version}` |
| `POST /api/runs/{uuid}/actions` | Core `{expected_run_version}` plus UUID `Idempotency-Key` |
| `GET /api/runs/{uuid}/actions` | Core visible Actions |
| `GET /api/actions/{uuid}` | Core Action snapshot |
| `POST /api/actions/{uuid}/authorize` | Core `{expected_action_version}` plus UUID key |
| `POST /api/actions/{uuid}/execute` | Core `{expected_action_version}` plus UUID key |
| `GET /api/handoffs` | Consumer persisted business records |
| `POST /api/policy/test` | Consumer `{operation: purge_incident_history or create_incident_handoff}`; policy check only |
| `GET /api/policy/evidence` | Consumer local mock decision evidence |

Use backend-returned versions. A normally validated Run awaits approval at version 4;
approval produces version 5. Admission produces Pending Action version 1; authorization
version 2; durable claim version 3; terminal result version 4. These are observed core
contracts, not a consumer state machine. No UI guesses or advances these versions.
Missing capability is 401; policy denial is 403; invalid contracts are 400; missing
idempotency key is 428; stale/conflicting state/key is 409. Failed planning can return a
201 **persisted PlanRejected Run**, so inspect its state/error, not HTTP success alone.

## Deterministic failure demos

Create a separate new state directory for each experiment. Fault switches require
explicit fixture mode and are startup configuration, never model/browser input.

```powershell
uv run safeops init --state .runtime/timeout-demo
uv run safeops serve --state .runtime/timeout-demo --provider fixture --fixture-fault timeout --predecessor-stopped --port 8766
```

Other planning faults: `invalid_json` and `unavailable`. Execution faults:
`--executor-fault policy_deny` (backend boundary denies the registered tool without a
handoff), and `--executor-fault post_commit_ack_loss` (one committed handoff, core
Unknown, no automatic redispatch). Stop the previous process before restarting against
the same directory. Remove fault switches to observe existing state without reprovisioning.

Direct executor/store tests additionally exercise a changed payload under the same
effect UUID, wrong adapter/target/version/scope, business identity corruption and
concurrent calls. Core integration tests hold an executor boundary open while replaying
the same command and attempting a conflicting claim, proving one dispatch. Recovery
tests cover both acknowledged success and an interrupted durable claim.

## Fresh installation

In a separate PowerShell process, choose a NEW ignored environment and use the lock:

```powershell
$env:UV_PROJECT_ENVIRONMENT = '.artifacts/fresh-venv'
uv sync --locked --no-editable
uv run --no-sync python -c "import agentic_intent_gate.runtime, safeops.main"
uv run --no-sync safeops init --state .artifacts/fresh-state
uv run --no-sync pytest -q tests/browser/test_e2e.py::test_happy_replay_refresh_and_mock_denial tests/browser/test_e2e.py::test_real_process_graceful_restart --basetemp=.artifacts/fresh-tests
```

The environment variable is process-local. Do not rerun initialization over an existing
state directory; fresh test directories and installations are explicitly isolated.

## Phase 2 changes

Implement an SDK-backed adapter at `integration/armoriq_boundary.py`, inject it from
trusted `integration/runtime_composition.py`, and keep mock tests offline. Obtain and
privately configure account/API credentials and end-user identity; select an SDK version
based on inspected signatures, register transport if needed, verify real allow/deny
policies, capture safe remote invocation/audit evidence and check competition rules.
Clarify service unavailability versus ambiguous invocation, policy holds, parameter
digests, timeouts and documented idempotency. None of those live integration gates are
satisfied by Phase 1. No real ArmorIQ integration tests exist or run in this phase.
