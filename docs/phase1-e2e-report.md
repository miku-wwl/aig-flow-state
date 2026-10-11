# SafeOps Agent — Phase 1 execution report

Verification date: **2026-10-11, Pacific/Auckland**. This report describes executed local
tests. ArmorIQ enforcement remains a deterministic **MOCK** in every scenario, including
the successful real-Ollama workflow. No live ArmorIQ account or sponsor API was used.

## A. Implementation summary

The previously clean repository contained only `AGENTS.md` and a minimal `README.md`.
`AGENTS.md` was preserved. README was updated; project metadata/lock, environment
example, ignores, `src/safeops`, consumer tests, browser verification and these three
documentation files were added. No staging, commit, push, tag, release or deployment
was performed.

FastAPI and vanilla HTML/CSS/JS implement one business workflow: incident handoff
creation. The browser renders backend snapshots and provides explicit Plan generation,
exact approval/rejection, Action admission, independent authorization and execution.
Capability handling is memory-only. Separate business SQLite data and the installed
shared Runtime provide the real local effects/control plane. No React build or generic
agent/MCP framework was added.

## B. Core integration and environment

| Item | Verified value |
| --- | --- |
| Python | CPython 3.13.9, Anaconda Windows x86_64 |
| OS | Windows 11, build 26200 |
| uv | 0.11.16 |
| Runtime distribution | `agentic-intent-gate==0.1.0` |
| Immutable Git commit | `fd742b783058a53400c465b4ab59c6e80715895a` |
| Annotated `v0.1.0` tag object | `ce0a516baf857bf79b53237677fff7fd3c50de95` |
| FastAPI / uvicorn | 0.143.0 / 0.54.0 |
| Playwright / browser | 1.63.0 / installed Google Chrome |
| Ruff | 0.17.0 |
| Ollama installed model | `phi4-mini:latest`, digest begins `78fad5d182a7` |
| Local service | `http://127.0.0.1:8765` |

Release verification was executed with:

```powershell
git ls-remote https://github.com/miku-wwl/agentic-intent-gate.git refs/tags/v0.1.0 'refs/tags/v0.1.0^{}'
uv venv --python 3.13 .venv
uv pip install --python .venv/Scripts/python.exe 'agentic-intent-gate @ git+https://github.com/miku-wwl/agentic-intent-gate.git@fd742b783058a53400c465b4ab59c6e80715895a'
uv sync
uv lock --check
```

Both `uv.lock` and installed `direct_url.json` resolve to the required commit. The
installed `runtime.py`, actual provider/Run/approval/Action HTTP contracts, verifier,
owner lock and executor protocol were read. The release's
[`examples/consumer/app.py`](https://github.com/miku-wwl/agentic-intent-gate/blob/v0.1.0/examples/consumer/app.py)
was read as the reference. It remains only an ignored reference artifact; its executor
and runtime source were not vendored into product code.

Public APIs used: `ToolBinding`, `ToolCapability`, `ExecutableRegistry`,
`CapabilityVerifier`, `BoundCapabilityAuthorization`, `open_runtime`, `Runtime.http_app`,
`provision_capability`, `ExecutionSpec`, `ToolOutcome`, `Outcome`. Consumer providers
implement `ModelProvider.generate_plan`. Tests also use `Intent`, `ActionCommand`,
`AdmissionCommand`, `ApprovalChoice`, `ApprovalDecisionRequest`, `AttemptContext` and
the repositories/services supplied by the public Runtime composition.

Trusted tool identity is `create_incident_handoff`, version `1`, target `incident-desk`,
adapter `safeops-armoriq`, binding revision `safeops-v1`, persisted execution scope.
The closed, flat schema accepts exactly `incident_id`, `summary`, `handoff_note`.
Extra fields, wrong identities/types, empty/oversized values and extra steps are rejected.

The demonstrated sequence is:

**Validated Plan → Persistent Run → Exact Human Approval → Trusted Admission →
Independent Authorization → Durable Claim → Consumer Executor → Mock Allow →
Committed Handoff → Receipt → Succeeded.**

The owner fence is held inside FastAPI lifespan. Startup never silently changes identity
or migrates databases. A second owner and a missing predecessor-stopped assertion are
rejected. All 42 installed core Python source files were hash-compared with a separate
fresh installation and matched. Core source was never edited.

## C. Local ArmorIQ simulation

`MockArmorIQClient` allows only the trusted handoff operation/scope/target. It denies
`purge_incident_history`. That operation has no executable business implementation.
The backend boundary also detects intent/payload mismatch and distinguishes
unavailability, timeout and ambiguous invocation. Tests verify distinct results and
no business effects for those failure modes.

The mock check runs inside the real executor after core authorization and durable
claiming. An injected local policy denial on the registered tool produces core `Failed`,
no success receipt and zero handoffs; the detailed `PolicyDenied` is retained in local
`policy_evidence`. The separate UI policy lab returns HTTP 403 with `mode: MOCK`,
`core_action_created: false`, `business_effect_executed: false` and writes local evidence.

The official [ArmorIQ Python SDK docs](https://docs.armoriq.ai/platform/sdk-cli/python-sdk)
and [Ollama OpenAI-compatible API docs](https://docs.ollama.com/api/openai-compatibility)
were inspected. The consumer enforcement interface is not represented as a real SDK
API, and mock decisions are not represented as real ArmorIQ enforcement.

## D. Databases and recovery

Private demo data: `.runtime/local/identity.json`, `.runtime/local/capability`,
`.runtime/local/gate.sqlite3`, `.runtime/local/effects.sqlite3`, all ignored by Git.
Capability contents were never printed. The private directory/file were provisioned
with Windows owner ACLs, using the core capability provisioner.

Observed core tables: `runs`, `approval_decisions`, `audit_events`,
`approval_plan_bindings`, `actions`, `action_authorizations`, `action_attempts`,
`action_command_receipts`, `action_events`. The consumer never directly writes them.
Business tables: `identity`, `handoffs`, `policy_evidence`.

Handoffs retain unique effect UUID, payload digest, store/binding identities, incident
fields, unique receipt UUID and creation time. `BEGIN IMMEDIATE` and uniqueness protect
concurrent calls. Exact store replay retains one receipt/row; a changed payload under
the same effect key fails without overwriting data. Both executor and store independently
reject wrong trusted scope/binding. Core command replay dispatches only once.

Graceful real-process restart verified different process IDs, exit code 0, unchanged
identity/capability hashes, unchanged receipt/records, and restored browser state.
An interrupted durable claim recovers as Unknown without dispatch. A post-commit
acknowledgement fault leaves one real business record and a core Unknown Action with
no confirmed success receipt. Replay/restart never redispatches the effect.

After real Ollama verification, the normal product CLI restarted against the same
identity/databases on port 8765. Authenticated HTTP reads confirmed the same Approved
Run, Succeeded Action and one business record; evidence is
`.artifacts/evidence/product-cli-restart.json`. Business `PRAGMA integrity_check` returned
`ok`. The live store contains exactly one handoff and two Runs: the completed Run and
an earlier valid AwaitingApproval Run from a browser-verifier interruption. That earlier
Run was retained and never authorized/executed.

## E. Real browser and scenario coverage

The UI is running at **http://127.0.0.1:8765** in Ollama mode. Select
`.runtime/local/capability` via **Load capability**, then open saved Run
`ce67e8f7-79ca-4e4f-a85d-80b780a082b8` to inspect the completed live verification.
Refreshing requires reloading the capability; restoration performs reads only.

| Scenario | Execution evidence | Result |
| --- | --- | --- |
| TC01 happy path | Real browser clicks, core Action + committed SQLite row + matching receipt | PASS |
| TC02 rejected approval | Browser reject and core admission rejection; no Action/effect | PASS |
| TC03 unauthorized execution | Browser deliberate execution attempt, backend 409, Pending unchanged, zero rows | PASS |
| TC04 stale/mismatched approval | Core HTTP version conflict and rejected Plan-substitution field | PASS |
| TC05 mock policy denial | Browser policy lab HTTP 403, local MOCK audit, no core Action/effect | PASS |
| TC06 idempotent replay | Browser exact request replay and matching persisted receipt, one row | PASS |
| TC07 payload conflict | Consumer executor same-key/different-input conflict; original row unchanged; core key/body conflict 409 | PASS |
| TC08 refresh persistence | Real reload, memory capability reloaded, same Action/receipt/record | PASS |
| TC09 restart recovery | Graceful uvicorn subprocess stop/restart, same DB/identity, browser recovery | PASS |
| TC10 provider failure | Browser timeout and invalid JSON error rendering; PlanRejected and zero effects | PASS |
| TC11 ambiguous outcome | Browser + core integration post-commit fault, Unknown + one row, no redispatch | PASS |
| TC12 concurrency | Browser approval/authorization followed by simultaneous real HTTP commands; core held-boundary claim race and store concurrency | PASS |

TC07 uses the trusted executor/store boundary for a forged effect identity; no production
API was added to let a browser override a compiled payload/effect key. TC12's simultaneous
execution requests are real HTTP after browser-controlled approval/authorization. The
held-boundary integration test separately forces overlap during an active core claim.

Sanitized real screenshots, visually inspected:

- `.artifacts/screenshots/01-plan-awaiting-approval.png`
- `.artifacts/screenshots/02-successful-action-receipt.png`
- `.artifacts/screenshots/03-simulated-policy-denial.png`
- `.artifacts/screenshots/04-persisted-after-refresh.png`
- `.artifacts/screenshots/live-plan-awaiting-approval.png`
- `.artifacts/screenshots/live-successful-action.png`

JSON evidence: `.artifacts/evidence/offline-browser.json`, `restart-browser.json`,
`unknown-browser.json`, `concurrent-http.json`, `live-ollama.json`,
`product-cli-restart.json`. No HAR/traces containing authorization headers were recorded.

## F. Executed checks and real Ollama

Focused suites were run while implementing and debugging. A stabilized regression
passed **65 tests**, and a subsequent independent store-scope guard passed **9 focused
store tests**. The final aggregate regression passed **66 tests, 0 failed, 0 skipped**
in **123.02 seconds**, including **8 real-browser tests**. The other 58 tests cover
planning, HTTP contracts, core integration, effects, policy boundaries and recovery.
JUnit evidence is `.artifacts/offline-regression.xml`.

```powershell
uv run pytest -q --junitxml=.artifacts/offline-regression.xml --tb=short
uv run ruff check
uv run ruff format --check
uv lock --check
node --check src/safeops/api/static/app.js
git diff --check
uv run python -m scripts.live_browser_check --state .runtime/local
```

Fresh environment commands executed in a separate PowerShell process:

```powershell
$env:UV_PROJECT_ENVIRONMENT = '.artifacts/fresh-venv'
$env:TEMP = (Resolve-Path '.artifacts/build-temp').Path
$env:TMP = $env:TEMP
$env:UV_LINK_MODE = 'copy'
uv sync --locked --no-editable
uv run --no-sync safeops init --state .artifacts/fresh-state
uv run --no-sync pytest -q tests/browser/test_e2e.py::test_happy_replay_refresh_and_mock_denial tests/browser/test_e2e.py::test_real_process_graceful_restart --basetemp=.artifacts/fresh-tests --junitxml=.artifacts/fresh-regression.xml --tb=short
uv sync --locked --no-editable --reinstall-package safeops-agent
```

Fresh browser verification: **2 passed, 0 failed, 0 skipped** in 32.16 seconds. Both core
and consumer resolved from the fresh environment's `site-packages`; consumer
`direct_url.json` reports `editable: false`. After the final store guard was added,
the fresh consumer was rebuilt, its installed store source hash matched current source,
and a real fresh-package HTTP startup/shutdown smoke test passed against the initialized
fresh state. No core checkout/PYTHONPATH injection was used.

Real headed-browser Ollama check: **PASS**. One genuine provider call received one model
response using discovered `phi4-mini:latest`. Generated JSON passed core validation,
was persisted, and completed explicit browser approval/admission/authorization/execution.
The Plan-generating Run transition took approximately 11.04 seconds from the persisted
timestamps, within the unchanged core request budget.

- Live Run: `ce67e8f7-79ca-4e4f-a85d-80b780a082b8`
- Live Action: `1a000a4d-f142-4d96-b9a7-1d3947e0cff2`, **Succeeded**, version 4
- Durable receipt: `b71ddf25-a66a-48b8-9cf7-069ee7dc2be7`
- Effect key: `d5ac5732-f89f-43e6-8749-17b8f8f2023d`
- Business commit timestamp: `2026-10-11T08:05:28.426608+00:00`
- Database count for this receipt: **1**; displayed/backend/store receipts matched.

Earlier failures were corrected, not skipped: Hatch required explicit permission for
Git direct dependency metadata; pytest's artifact parent needed creation; a frontend
handler had a syntax error; tests needed `text_content()` for collapsed JSON panels;
the live browser verifier's string evaluation conflicted with the production CSP;
session-scoped sync Playwright kept an event loop active across pytest-asyncio tests.
The fixes retained the CSP and core safety checks, used function-scoped browser lifetime,
and used concurrent HTTP threads instead of nested event loops. The initial full-suite
attempt reported 23 failures from that test-loop conflict, followed by a passing 65-test
regression. A fresh wheel build initially encountered a Windows PE-resource access error;
an isolated workspace temp directory and copy linking allowed the locked install to finish.

One non-failing dependency warning remains: Starlette deprecates its TestClient httpx
transport and recommends httpx2. This was not suppressed. Real uvicorn/browser tests
and the live Ollama workflow passed independently of TestClient.

## G. Phase 2 handoff and limitations

Replace/inject the SDK-backed consumer adapter at
`src/safeops/integration/armoriq_boundary.py` and trusted
`src/safeops/integration/runtime_composition.py`. Obtain account/API configuration,
select/pin an SDK after signature inspection, configure user identity, determine MCP
transport/registration, install real allow/deny policies and collect real invocation
and policy-audit evidence. Review enforce-only versus proxy invocation, effect ownership,
token expiry/holds, parameter binding, timeout ambiguity and documented idempotency.

Runtime scope remains one trusted SIDE_EFFECT tool and single-step execution. There is
no arbitrary MCP execution, production multi-user authentication, distributed HA,
remote exactly-once guarantee, automatic Unknown retry/reconciliation or cloud deployment.
Provider timeout cannot exceed the pinned core HTTP budget. Transport errors use the
public module's generic core error plus consumer-specific safe status details.

**Ready for Phase 2 means the verified Phase 1 baseline is ready for real integration
work. It does not mean live ArmorIQ or competition submission readiness.** Real ArmorIQ
tests were NOT RUN by Phase 1 design; no credentials or real SDK invocation were used.

## H. Final verification gates

All statuses below refer to the verified local Phase 1 scope.

| Gate | Result |
| --- | --- |
| PYTHON_313 | PASS |
| PINNED_RUNTIME | PASS |
| RUNTIME_PUBLIC_API | PASS |
| OLLAMA_PROVIDER_IMPLEMENTED | PASS |
| DETERMINISTIC_PROVIDER | PASS |
| STRICT_PLAN_VALIDATION | PASS |
| PERSISTENT_RUN | PASS |
| EXACT_APPROVAL | PASS |
| INDEPENDENT_AUTHORIZATION | PASS |
| ACTION_EXECUTION | PASS |
| MOCK_ARMORIQ_BOUNDARY | PASS |
| MOCK_POLICY_DENIAL | PASS |
| DURABLE_BUSINESS_EFFECT | PASS |
| IDEMPOTENT_REPLAY | PASS |
| CONFLICT_REJECTION | PASS |
| UNKNOWN_HANDLING | PASS |
| RESTART_RECOVERY | PASS |
| HTTP_API | PASS |
| BROWSER_E2E | PASS |
| LIVE_OLLAMA_E2E | PASS |
| FRESH_ENVIRONMENT | PASS |
| RUFF | PASS |
| DOCUMENTATION | PASS |
| NO_CORE_MODIFICATIONS | YES |
| PHASE1_OFFLINE_E2E | PASS |
| PHASE1_LIVE_LOCAL_E2E | PASS |
| READY_FOR_PHASE2 | YES |

Ruff lint/format, lock consistency, JavaScript syntax, diff whitespace checks and the
public-source capability scan passed. Git's index remained empty of staged changes;
`AGENTS.md` remained unchanged. Evidence/private state directories remain ignored.
The server is deliberately left running locally for review, in Ollama mode, using the
already initialized `.runtime/local` identity and databases.
