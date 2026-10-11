# Aegis Relay — Development and reproduction

Phase 2 adds explicit `SAFEOPS_ENFORCEMENT_MODE=mock|real` (default mock),
`safeops init-live`, and a separate loopback-only `safeops mcp` service. See
[the current setup](phase2-setup.md) and [architecture decision](phase2-architecture.md).
The existing identifiers and SQLite schemas below remain unchanged. In real mode,
`/api/policy/test` permits only the nondestructive canary; writes through this route
are CORE_DENIED. `/api/policy/evidence` reads the separate private live audit store.

**Trust the intent. Govern the action.** A permissioned AI agent for secure incident
handoffs, built for Flow State — AI Agent & MCP Hackathon, organized by ArmorIQ.
Phase 1's mock workflow remains the default. Phase 2's real SDK/MCP execution path
is implemented. Real registration and canary denial were verified; a real handoff
ended Unknown. See the current report for the remaining platform/audit blockers.

## Branding and compatibility

Aegis Relay is the product name. Stable programmatic identifiers retain their original
names so existing installations, configuration, saved Runs and browser restoration work:

| Preserved identifier | Compatibility reason |
| --- | --- |
| `safeops-agent`, `safeops`, `safeops.main:main`, `src/safeops` | Installed distribution, CLI, imports and package layout |
| `SAFEOPS_STATE`, `SAFEOPS_PROVIDER`, `SAFEOPS_OLLAMA_URL`, `SAFEOPS_MODEL`, `SAFEOPS_MODEL_TIMEOUT` | Existing environment configuration |
| `OllamaSafeOpsProvider`, `safeops_plan`, `safeops-static` | Internal class, model schema name and static route name |
| `safeops-armoriq`, `safeops-v1` | Persisted ToolBinding adapter and revision |
| `safeops-local-operator`, `safeops-policy-v1` | Persisted subject and authorization policy revision |
| `safeops-run-` | Scope-qualified browser restoration key; contains only a Run UUID |
| `create_incident_handoff`, `incident-desk`, `/api/*`, JSON fields and SQLite tables | Existing tool, target, API and data contracts |

Execution scopes, store IDs, effect keys, capabilities and existing database contents
are preserved. Rebranding requires no migration or reprovisioning. Agentic Intent Gate
v0.1.0 remains pinned to `fd742b783058a53400c465b4ab59c6e80715895a`.

Restart an existing server after updating source to refresh its in-memory backend
metadata. Keep its existing state directory; do not rerun initialization or reset data.

## Local verification

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
| `POST /api/policy/test` | Mock policy check; real mode probes only the nondestructive canary and rejects writes |
| `GET /api/policy/evidence` | Private mock decision evidence or separate sanitized live audit |

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

`integration/live_armoriq.py` owns actual SDK capture/token/invoke and receipt verification;
trusted runtime composition explicitly chooses mock or real. `integration/dispatch_permit.py`
binds a claimed, authorized core Action to the protected `mcp/server.py`. The mock
check-only protocol remains separate. Real setup is explicit, uses existing credentials
and never silently falls back to mock. Offline SDK/browser tests carry an explicit
OFFLINE SDK TEST badge and are distinct from opt-in platform evidence. See the
[architecture](phase2-architecture.md), [setup](phase2-setup.md), and
[qualification report](phase2-e2e-report.md) for commands, classifications and actual results.
