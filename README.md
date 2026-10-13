# Aegis Relay

**Trust the intent. Govern the action.**

A permissioned AI agent for secure incident handoffs.

Built for **Flow State — AI Agent & MCP Hackathon**, organized by **ArmorIQ**.
The redesigned console makes the separate Plan, Approval, Admission,
Authorization, SDK preparation and execution stages visible. Its timeline and
receipt summary display backend evidence; they do not grant permissions.

The V4 reference completed one real phi4-mini/ArmorIQ SDK-only handoff using
this redesigned console and fresh human gates. Independent verification found
one execution attempt, one SQLite handoff, Core Action Succeeded and a matching
durable receipt. Authenticated Platform readback matched the new report and
showed its allowed/Success row; a separate historical purge denial remains
clearly labelled. The V4 artifacts are private, ignored files under
`.artifacts/final-submission/v4-redesigned-ui/`. The final competition video
still requires the operator's own fresh execution and real English voice.
No video has been uploaded and no competition entry has been submitted. Qualification-time statements in
[historical reports](docs/phase24-application-e2e-report.md) remain unchanged.

The shared Core is a pre-existing project dependency maintained by the same
operator. It is reused through its pinned public API; Core development is not
claimed as work completed during this hackathon. The incident product/UI, Ollama
provider and ArmorIQ consumer integrations are the competition-specific work.

Phase 1 is a local, single-operator application for one workflow: creating a synthetic
incident handoff. A real Ollama model proposes a bounded Plan. You review the persisted
Plan, approve or reject it, admit an Action, authorize it independently, and execute it.
The final receipt identifies a committed SQLite business record.

The application consumes the installed **Agentic Intent Gate 0.1.0** package, pinned to
`fd742b783058a53400c465b4ab59c6e80715895a`. The annotated `v0.1.0` tag was verified to
resolve to that commit. Core validation, exact approval binding, authorization, durable
Action claiming, CAS, idempotency receipts and recovery belong to that shared package.
No core source is copied or modified.

Enforcement defaults to **mock**, preserving the Phase 1 workflow. Explicit `proxy`
(legacy `real` remains an alias)
mode uses pinned `armoriq-sdk==0.6.10`, a signed core dispatch permit and a separate
protected MCP. ArmorIQ proxy execution owns the single business write, and the
consumer verifies its receipt against the durable store. Missing configuration fails
closed. Real authentication, temporary public MCP discovery, agent/MCP registration
and a genuine canary policy denial were verified on 11 October 2026. The single
historical proxy handoff attempt obtained a platform Plan ID but ended Unknown,
with zero local business records. It was not retried. The temporary tunnel is retired.
Local SDK transport tests do not prove real cloud execution.

Explicit **`sdk-only`** uses the already qualified Phase 2.3 adapter in this same
application: after exact Approval and independent Authorization, explicitly prepare
an in-memory ArmorIQ Plan/token. Core then claims execution under its frozen
five-second limit; actual HTTPS SDK policy enforcement must return explicit Allow
for the expected policy. Exact Plan/arguments/binding/Action and a late signed permit
are independently verified locally. Only the SDK-only consumer executor writes to
the existing business SQLite store. SDK `report` and `complete_plan` run after Core
Succeeded. Audit failure is separate from business success and cannot repeat the write.
No public MCP, custom domain, tunnel or deployment is needed for this mode.

The remote Allow is a **tool-level policy decision**. It does not prove remote
argument or permit integrity. SDK-only tokens remain server memory only; expiry or
restart requires explicit preparation of a still Authorized, never executed Action.
Unknown Actions cannot be prepared or retried. Historical operator screenshots
verify visible cloud rows and the Phase 2.3 API request/Action/receipt correlation;
their row UUID is unverified and they are not new Phase 2.4 browser evidence.
See [Phase 2 architecture](docs/phase2-architecture.md),
[setup and approval scope](docs/phase2-setup.md),
[current evidence](docs/phase2-e2e-report.md),
[Phase 2.1 diagnosis](docs/phase2-blocker-diagnosis.md),
[submission draft](docs/submission.md), and
[demo script](docs/demo-script.md).

Historical Phase 2.1 fixes and the optional protected MCP/proxy route are preserved.
The [SDK-only qualification](docs/phase23-sdk-only-qualification.md) established
execution feasibility; Phase 2.4 adds application/UI integration without Core edits.

## Start locally

Requires Python 3.13, [uv](https://docs.astral.sh/uv/), authenticated Git if the runtime
repository is private, and a browser. Run in this repository with PowerShell:

The stable `safeops` CLI and Python package names are retained for compatibility;
see [the preserved identifiers](docs/development.md#branding-and-compatibility).

```powershell
uv sync --locked
uv run safeops init --state .runtime/local
uv run safeops serve --state .runtime/local --provider ollama --predecessor-stopped
```

`init` requires a **new** directory and refuses to overwrite existing state. If this
workspace already contains the verification demo's `.runtime/local`, omit `init`.
It creates an ACL-private capability file, stable identity, business database and core
database. An interrupted initialization is preserved for inspection; choose a new
directory rather than resetting existing data.

Before using `--predecessor-stopped`, stop every previous server using the same state
directory. This is the core's required operator assertion, alongside its lifetime-held
OS owner lock. Use one worker, without reload. Ctrl+C stops the foreground server.

Open **http://127.0.0.1:8765**. Click **Load capability** and select
`.runtime/local/capability` with the file picker. Its contents stay only in browser
memory; no token appears in HTML, URLs, logs, screenshots or localStorage. You must
reload the file after refreshing. The browser remembers only the selected Run UUID,
namespaced by execution scope, and restores it with GET requests.

1. Enter an incident request containing an `INC-number`, then generate and save the Run.
2. Review incident ID, summary, handoff note, `Full structured Plan JSON`, validation and `SIDE_EFFECT` risk.
3. Approve the exact Plan, or reject it without creating an Action.
4. Admit the approved Action. This leaves it `Pending`.
5. Authorize the Action. This leaves it `Authorized`, with no business effect yet.
6. Execute once. Match the `Succeeded` receipt with the persisted handoff record.
7. Refresh, reload the capability and click **Open Run** with the saved UUID to
   observe the preserved state using read-only requests. For a live reference,
   do not replay or dispatch another Action to improve the recording.

For SDK-only, exclusively initialize **new** private state, provision its local
dispatch keys/audit store, and use existing ArmorIQ CLI credentials:

```powershell
uv run safeops init --state .runtime/sdk-only-demo
uv run safeops init-live --state .runtime/sdk-only-demo
uv run safeops serve --state .runtime/sdk-only-demo --provider ollama --enforcement-mode sdk-only --predecessor-stopped
```

After step 5, click **Prepare SDK-only execution**, then **Execute once** while the
stage is READY. Preparation has no business effect. Expired or restart-lost stages
require a new explicit click; no automatic token refresh happens. Do not use old
Unknown state or replay historical INC-23001. A live business write requires exact
human approval of the synthetic Plan. SDK-only's canary viewer labels the preserved
Phase 2.2 remote denial as historical and makes no new policy request.

| Config value | Execution | Label |
| --- | --- | --- |
| `mock` (default) | Simulated policy, local store | LOCAL / MOCK |
| `sdk-only` | Actual SDK remote tool policy, verified local writer | ARMORIQ SDK-ONLY LIVE |
| `proxy`, legacy `real` | Existing ArmorIQ proxy/MCP writer | PROXY LIVE |
| Injected test transport | Actual SDK with explicitly offline HTTP transport | LOCAL / OFFLINE SDK TEST |

For a visible safe denial, admit an Action and click **Test execution without
authorization**, or use **Test simulated forbidden operation** in the mock policy lab.
The latter requests `purge_incident_history`: local policy denies it, records mock
evidence, creates no core Action, and executes no business operation. There is no purge
executor. Core tool rejection and mock policy denial are separate mechanisms.

## Ollama and deterministic modes

Run `ollama list` to discover installed tags. The provider queries `/api/tags` and uses
an installed `phi4-mini` tag; `phi4-mini:latest` was present on this host. Configure
`SAFEOPS_MODEL` when selecting another installed phi4-mini tag. The local
OpenAI-compatible `/v1/chat/completions` endpoint receives a structured schema and one
request. Raw output is validated by the core, without extraction, repair, retries or
cloud/fixture fallback. Models are never downloaded by Aegis Relay.

The configurable provider timeout, `SAFEOPS_MODEL_TIMEOUT`, must be between 0 and 28
seconds because the pinned core HTTP planning budget is 30 seconds with a reserve.
Only loopback HTTP Ollama URLs are accepted. See [.env.example](.env.example); these
are environment variables, not a file automatically loaded by the application.

Offline mode is explicit and visibly labelled:

```powershell
uv run safeops serve --state .runtime/local --provider fixture --predecessor-stopped
```

The deterministic provider is a test fixture, not a model. Changing provider does not
reprovision identity or data. Missing Ollama/model, timeouts, invalid JSON or validation
failures produce an error and a persisted `PlanRejected` Run without an Action.

## Verification

Real Chrome is used through Playwright. Install Chrome locally, or adapt the test
browser channel to an explicitly installed Chromium. No browser download is performed
by the test runner.

```powershell
uv run pytest -q                     # complete offline regression, including real browsers
uv run ruff check
uv run ruff format --check
uv lock --check
node --check src/safeops/api/static/app.js  # optional JS syntax check if Node is installed
uv run python -m scripts.live_browser_check --state .runtime/local
```

The last command performs a **separate headed-browser, real Ollama** workflow and adds
one reviewed synthetic handoff to the specified private store. It starts and gracefully
stops a real uvicorn process. If the directory does not exist, this explicit verification
command initializes it. Do not run it against state already owned by another server.

Test databases, sanitized screenshots and JSON evidence remain ignored under
`.artifacts/`. Private demo state remains ignored under `.runtime/`. No HAR or browser
trace with authorization headers is recorded. See
[the execution report](docs/phase1-e2e-report.md) for actual results and evidence paths,
[architecture](docs/architecture.md) for gate ownership, and
[development](docs/development.md) for API and fault-reproduction details.

To preserve historical test evidence, set `SAFEOPS_TEST_ARTIFACTS` to a **new**
ignored directory and pass a fresh `--basetemp`, `--junitxml` and pytest cache directory.
The SDK-only qualification driver is `scripts/sdk_only_browser_check.py`; it opens
real Chrome, reviews a fresh real Ollama Plan, and waits for a closed approval file
matching the Run and exact arguments. It never infers approval from timeout or EOF.
Its optional resume opens the same unapproved Run with zero Actions/effects, or
the exact still Authorized, never executed Action after a preparation interruption.
Keep the output private and authorize the exact one write before supplying approval.

## Limits and Phase 2

One trusted `create_incident_handoff` v1 tool, target `incident-desk`, adapter
`safeops-armoriq`, binding revision `safeops-v1`. No multi-step orchestration, general
MCP execution, production authentication, distributed HA or remote exactly-once claim.
Separate approved Runs represent separate intended handoffs; idempotency protects an
Action/effect identity, not every repeated natural-language request.

After a post-commit acknowledgement failure, the Action is `Unknown` even if the
business viewer shows a record. It has no confirmed success receipt. Refresh/restart
never redispatches it. Aegis Relay exposes no automatic reconciliation or retry for Unknown.

Phase 2 implements a separate SDK proxy adapter and protected MCP. The official
[ArmorIQ Python SDK documentation](https://docs.armoriq.ai/platform/sdk-cli/python-sdk)
and installed 0.6.10 API were inspected; its actual capture/token/invoke flow is used.
Historical proxy forwarding remains unqualified; its Unknown is preserved. SDK-only
qualification and new application results are separate in the Phase 2.4 report.
Mock results alone do not establish competition readiness. No submission has occurred.
