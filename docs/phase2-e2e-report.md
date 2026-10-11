# Phase 2 qualification — 11 October 2026

**Latest addendum: Phase 2.1, 12 October NZDT / 11 October UTC.** This file's original
Phase 2 results below remain historical. Current diagnosis and source changes are
in [phase2-blocker-diagnosis.md](phase2-blocker-diagnosis.md). Current tests: **128
passed**, including all previous 108 cases and **11 Chrome tests**, in 232.27 seconds.
Local authentication/protocol repairs pass; refreshed cloud inventory still has
zero tools and the retired endpoint. No fresh real token, Action or invoke was run.
The 22 files of original Unknown state and 52 Phase 1 protected files are unchanged;
installed core files and pin are unchanged. No deployment/DNS/registration/policy
mutation or commit/push occurred in Phase 2.1.

## Phase 2.1 diagnostic states

| Diagnostic | Status | Evidence |
| --- | --- | --- |
| MCP_LOCAL_PROTOCOL | PASS | Real loopback independent parser/CLI, negotiation, IDs, framing, valid schemas. |
| MCP_LOCAL_AUTH | PASS | Missing/wrong/duplicate/non-ASCII credentials denied; valid single Bearer accepted. |
| MCP_EXTERNAL_SSE | BLOCKED | No approved active stable endpoint. |
| MCP_EXTERNAL_AUTH | BLOCKED | Same prerequisite; historical tunnel proof is not current. |
| ARMORIQ_DISCOVERY | FAIL | Fresh bootstrap/schema/toolMap counts all 0. Replacement endpoint cloud probe NOT RUN. |
| REGISTERED_AUTH_METHOD | UNVERIFIED | SDK reads do not expose it; reported OAuth display was not inspected live. |
| ARMORIQ_TOOL_COUNT | FAIL | Registered count 0 versus local 2. |
| POLICY_TARGET_ASSOCIATION | BLOCKED | SDK target matches original MCP; enabled/active/explicit override unverified. |
| REAL_PROXY_INVOKE | BLOCKED | Old result Unknown retained; no fresh real attempt. |
| CORE_EXECUTION_BUDGET | BLOCKED | Effective limits/source inspected and offline stages measured; current real route unmeasured. |
| REMOTE_AUDIT_VISIBILITY | BLOCKED | No connected authenticated Dashboard; prior SDK-key routes 401. |

## Phase 2.1 final gates

```text
CORE_RUNTIME_UNCHANGED=YES
BRAND_AEGIS_RELAY=PASS
PHASE1_REGRESSION=PASS
MCP_LOCAL_AUTH=PASS
MCP_LOCAL_PROTOCOL=PASS
MCP_LOCAL_TOOL_COUNT=2
MCP_EXTERNAL_SSE=BLOCKED
MCP_EXTERNAL_BEARER=BLOCKED
MCP_CLOUD_AUTH_MAPPING=BLOCKED
MCP_CLOUD_DISCOVERY=FAIL
REGISTERED_TOOL_COUNT=0
REGISTERED_ENDPOINT_CURRENT=NO
REAL_ALLOW_POLICY=BLOCKED
REAL_DENY_POLICY=BLOCKED
REAL_POLICY_DENIAL=PASS
CORE_EXECUTION_BUDGET=BLOCKED
FRESH_REAL_ALLOWED_ACTION=BLOCKED
ONE_DURABLE_EFFECT=BLOCKED
MATCHING_RECEIPT=BLOCKED
NO_DOUBLE_WRITE=PASS
OLD_UNKNOWN_PRESERVED=YES
REMOTE_ARMORIQ_AUDIT=BLOCKED
LIVE_BROWSER_E2E=BLOCKED
FULL_REGRESSION=PASS
SECRET_SCAN=PASS
PHASE2_REAL_E2E=BLOCKED
READY_TO_SUBMIT=NO
ACTUALLY_SUBMITTED=NO
```

REAL_POLICY_DENIAL reuses the original genuine canary denial against the unchanged
target context; it is not a new probe or proof of active explicit Dashboard deny.
NO_DOUBLE_WRITE and browser regression PASS are offline safety evidence. The one
effect/receipt gates above require a **fresh real** successful Action, which was
not attempted while prerequisites remain blocked. No submitted or live qualification
claim follows from the passing source/test archive checks.

The remainder preserves the original Phase 2 report and its earlier gates.

**PHASE2_REAL_E2E=BLOCKED · READY_TO_SUBMIT=NO · ACTUALLY_SUBMITTED=NO**

Local implementation and regression pass. Real registration and a genuine canary
policy denial are verified. The single real handoff attempt ended **Unknown**,
with zero local business records and no confirmed receipt. It was not retried.
Dashboard policy status and remote audit remain unavailable. Operator approval for
the temporary protected MCP exposure and narrow cloud setup was received and used.
No Phase 2 commit, push, tag, release, paid resource or competition submission occurred.

## A. What changed

| Files | Purpose |
| --- | --- |
| AGENTS.md | Replace only the authorized stale release-pin placeholder and setup wording. |
| pyproject.toml, uv.lock | Pin armoriq-sdk==0.6.10; preserve the immutable core dependency. |
| .env.example, armoriq.yaml | Explicit mock/real selection and actual SDK-schema registration template with credential references only. |
| src/safeops/configuration.py, main.py | Fail-closed real startup, explicit init-live and loopback-only mcp CLI, existing authenticated execution-route Action hint. |
| src/safeops/integration/runtime_composition.py | Trusted adapter selection, public runtime binding and SDK cleanup. |
| src/safeops/integration/armoriq_boundary.py | Retain the separate mock check-only protocol. |
| src/safeops/integration/armoriq_mapping.py | Exact approved step/parameter capture, stable MCP/tool names and strict receipt extraction. |
| src/safeops/integration/dispatch_permit.py | Explicit private provisioning and short signed dispatch bound to a core-claimed authorized Action, exact binding/payload/store. |
| src/safeops/integration/live_armoriq.py, live_audit.py | Actual SDK token/invoke, single forwarding, durable receipt verification, sanitized failure/Unknown and canary evidence. |
| src/safeops/mcp/__init__.py, server.py | Separate authenticated bounded JSON-RPC MCP, handoff executor and permanently nondestructive canary. |
| src/safeops/execution/handoff_executor.py | Return from real forwarding before the existing mock/local persist path. |
| src/safeops/api/routes.py, static/app.js, static/index.html | Actual mode/connectivity/registration/evidence display; explicit OFFLINE SDK TEST label; real policy lab restricted to canary. |
| scripts/armoriq_preflight.py, phase2_live_check.py | Isolated actual CLI preflight and opt-in platform/browser qualification; preserve partial failures and resume only an unapproved Run. |
| tests/armoriq_harness.py, test_live_armoriq.py, test_mcp_network.py, mcp_server_process.py | Actual SDK over explicitly offline transport, protected MCP/network/CLI checks, faults and core/effect safety. |
| tests/e2e_server.py, server_harness.py, browser/test_live_mode.py | Three added real Chrome flows for success, denial and post-commit Unknown over offline platform transport. |
| README.md; docs/architecture.md, development.md, phase2-architecture.md, phase2-setup.md, this report, submission.md, demo-script.md | Current truthful status, architecture, reproduction, evidence, copy-ready submission draft and 2–3 minute script. |

Historical Phase 1 report/artifacts are preserved. Execution evidence remains ignored
beneath .artifacts/phase2-20261011/ and is not staged.

## B. Brand and compatibility

Brand: **Aegis Relay**. Tagline: **Trust the intent. Govern the action.** Description:
**A permissioned AI agent for secure incident handoffs.** No further rebrand.

Preserved: safeops-agent, safeops, safeops.main:main, src/safeops; existing SAFEOPS_*
variables; OllamaSafeOpsProvider, safeops_plan, safeops-static; adapter/revision
safeops-armoriq/safeops-v1; subject/policy safeops-local-operator/safeops-policy-v1;
browser key prefix safeops-run-; create_incident_handoff v1, incident-desk, /api/*,
persisted JSON fields, SQLite schemas, existing scopes/store/effect identities and
private data. New cloud names aegis-relay/aegis-relay-mcp do not rename these contracts.

## C. Frozen core

Installed agentic-intent-gate **0.1.0**, immutable commit
**fd742b783058a53400c465b4ab59c6e80715895a**. Fresh annotated v0.1.0 verification
resolved to this commit. Actual installed public API and core consumer example were
inspected before implementation. Lock/installed direct URL resolve to the same pin.
Validation, Run/exact approval, authorization, durable claiming, CAS, idempotency and
recovery remain owned by the core.

The original and isolated installed core's **42 Python files match**; **52 protected
baseline files remain unchanged**. No core copy, monkeypatch, edit, database migration/
reset or shared-runtime repository change. Existing Phase 1 server/state are preserved.
Git HEAD remains **3003a38c16ecec18ac5b8bfd24adc26bd6e08657**; Phase 2 is uncommitted.

## D. Real ArmorIQ integration

SDK **0.6.10**, actual constructors/return fields and CLI schema inspected. Execution
uses capture_plan → get_intent_token(validity_seconds=10) → one invoke. This actual
proxy call owns forwarding; no enforce-then-local-write path, mock fallback, automatic
hold/reinvoke loop or ambiguous retry. HTTPS/TLS verification is enabled, redirects
disabled and max_retries=0. No new key/login/organization.

Existing credentials authenticated /iap/sdk/bootstrap. Actual CLI validate and
register --dry-run passed with isolated child USERPROFILE. Non-dry-run register ran
once. Fresh refresh_bootstrap() and list_mcps() verified resources; a cached
pre-registration bootstrap response was not used as final registration proof.

| Resource | Verified ID / observation |
| --- | --- |
| Agent aegis-relay | 2a9ea47b-0261-47d4-9670-d45118d7778a |
| MCP aegis-relay-mcp | 0b4133a0-9acd-451b-84a2-a795d9c593c5 |
| Policy cli-aegis-relay-aegis-relay-mcp | c4b4d803-aefd-4c74-bc0c-dbb4564d399c |
| SDK resolve_user policy context | mcp_server, exact MCP ID above, priority 100, allowedTools=[create_incident_handoff], defaultEnforcementAction=block. |

The template explicitly includes allow handoff / deny canary. The control plane
returned an allow-list/default-block representation. Dashboard active status and
explicit deny rule were **not verified**; assigned-policy gate remains BLOCKED
conservatively. No organization-wide policy profile changed.

Official cloudflared **2026.10.0** Windows amd64 matched published SHA256
86aee4017b26625cee8484c113558f48effa4cd47f7aa05fcf425604e5d2b23c.
Only 127.0.0.1:8766 was exposed. Public HTTPS initialize/tools-list and installed CLI
discovery found exactly the handoff and canary with the separate bearer.
Unauthenticated /mcp returned **401**; public root returned **404**. UI stayed local.
The temporary tunnel and separate MCP are stopped after testing; cloud registration/
policy remain, pointing at a retired test URL.

[Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
exclude general SSE support. This finite single-event response passed public discovery;
it does not prove persistent SSE or successful ArmorIQ forwarding. Remote tool
inventory remained empty despite direct discovery finding both tools. Routing/
credentials/transport diagnosis still needs actual platform evidence.

## E. Effect safety

In real mode **only mcp/server.py calls HandoffStore.persist**. The operator adapter
verifies the receipt against durable business data and never writes a second effect.
Mock retains its separate original local-write path. After core claiming, permit
issuance reads the public Action and requires Executing, independent authorization,
exact compiled spec and effect identity. MCP independently checks service bearer,
signature, short expiry, closed schema, full binding/scope/store and payload digest.

Existing store duplicate/conflict behavior is reused. Receipt identity alone is
insufficient; persisted payload/binding/store must match. Canary has no deletion code.
Approval cannot authorize execution; bearer possession cannot create a valid core
permit. Unknown is durable and never automatically retried/reconciled. No guaranteed
exactly-once remote effect is claimed.

## F. Actual live evidence

One real model response created Run **1946a97b-29d6-4307-9664-a2aba7517add** in
AwaitingApproval. The first runner's default five-second browser expectation ended
early while planning completed; no Action existed. The runner was corrected to an
explicit 35-second expectation and resumed that same unapproved Run. It did not
regenerate/repair the Plan or retry an effect.

A separately captured valid purge_incident_history intent received genuine explicit
ArmorIQ policy denial: **PASS**. Consumer event d1d3a52f-b60e-483a-8f50-3cd51cbe1181
records ARMORIQ_POLICY_DENIED at 2026-10-11T10:10:31.570332+00:00. This is a **local
audit event**, not a remote audit ID. Verification requires explicit block/deny or
denied-tool metadata: generic SDK 403, mismatch and local canary rejection do not
qualify. This probe created no core Action or effect; before/after counts were zero.

Headed Chrome reviewed, exactly approved, admitted and independently authorized the
saved Run. Pre-authorization execution was refused with zero effects. One actual
allowed-path invoke was attempted:

| Correlation | Actual result |
| --- | --- |
| Core Action | 3b1930f9-d28e-4b0d-8563-287108cbfd79, version 4, **Unknown** |
| Platform Plan | 707bb43b-5159-417a-b8a7-f6895cc55b37 |
| Effect key | 6b3640a8-4d4f-4a8a-9e80-4fc4fbd0a5d9 |
| Consumer classification | UNAVAILABLE after token issuance / invoke path |
| Confirmed receipt | None |
| Local business effects | **0** |

Forwarding cause is unverified. No further write invocation occurred. Read-only Chrome
restore/refresh and real-process restart retained Unknown, zero records and unchanged
audit: **PASS**, no redispatch. This does not turn Unknown into confirmed no remote
effect or authorize a retry.

Browser tools repeatedly reported zero available browsers; Chrome and in-app browser
were unavailable, including after the operator selected connecting an existing session.
Read-only policy-detail, platform Plan and Merkle requests returned **401** with SDK
credentials. The documented [API authentication split](https://docs.armoriq.ai/platform/api-reference)
distinguishes JWT dashboard routes. No new login/key was attempted. Actual dashboard
policy/audit screenshots and forwarding diagnosis remain BLOCKED.

Ignored evidence: public-probe.json, real-registration.json, fresh
registration-verification.json, policy-inspection.json, platform-read-evidence.json,
real-platform-attempt-1/real-evidence.json, real-platform-attempt-2/real-evidence.json,
real-platform-attempt-2/real-allowed-attempt.png, real-unknown-restored.png and
unknown-recovery.json. No raw intent tokens/API keys/capabilities/signing keys are
published. Screenshots were visually inspected.

## G. Commands and tests

Python **3.13.9**, isolated ignored uv environment:

~~~powershell
$env:UV_PROJECT_ENVIRONMENT = 'D:/workshop/oct/aig-flow-state/.artifacts/phase2-20261011/venv'
$phase2Python = "$env:UV_PROJECT_ENVIRONMENT/Scripts/python.exe"
uv sync --locked
uv lock --check
& "$env:UV_PROJECT_ENVIRONMENT/Scripts/ruff.exe" check src tests scripts
& "$env:UV_PROJECT_ENVIRONMENT/Scripts/ruff.exe" format --check src tests scripts
node --check src/safeops/api/static/app.js
git diff --check
~~~

All PASS. Lock resolves 40 packages; Ruff checks/formats 38 source files. Tests ran
from the ignored verification directory with junctions to repository tests/scripts,
preserving historical root artifacts. Final complete command:

~~~powershell
& $phase2Python -m pytest D:/workshop/oct/aig-flow-state/tests -q --basetemp=D:/workshop/oct/aig-flow-state/.artifacts/phase2-20261011/release-final-test-state --junitxml=D:/workshop/oct/aig-flow-state/.artifacts/phase2-20261011/release-final-pytest.xml -o cache_dir=D:/workshop/oct/aig-flow-state/.artifacts/phase2-20261011/release-final-cache --tb=short
~~~

**108 passed, 1 warning, 227.54 seconds**: 66 Phase 1 retained, 42 added. **11 actual
Chrome tests**: eight baseline and three new offline-SDK live-path tests. Retained
Starlette TestClient deprecation is not a failure. Targeted post-live checks also
passed **41 tests in 95.42 seconds** with the same command substituting
tests/test_live_armoriq.py and tests/browser/test_live_mode.py, separate
post-live-test-state, post-live-pytest.xml and cache. Final full run includes them;
these counts do not add.

Coverage: core gates/single claim, exact parameters, unknown tool, wrong binding/
target/scope, stale approval, service auth, forged/missing/expired permits, duplicate/
conflicting effects, block/hold, generic 403, token errors, mismatch, timeout/5xx,
missing/misbound receipts, lost acknowledgement, late token/cancellation, refresh
and restart. Offline policy replies/writes are not real cloud enforcement evidence.

Separate actual headed-Chrome/Ollama check:

~~~powershell
& $phase2Python -m scripts.live_browser_check --state D:/workshop/oct/aig-flow-state/.artifacts/phase2-20261011/ollama-state
~~~

**PASS**, real phi4-mini:latest with mock enforcement and one durable record. Action
68ad723b-e4a1-4751-9bc8-5c3ff03e448c; receipt 3ef62f4b-37f2-4429-9044-40bc51065aa6.
This separate local success is not the real ArmorIQ Action's result.

Actual public preflight and platform attempt commands, whose test URL is now retired:

~~~powershell
& $phase2Python -m scripts.armoriq_preflight --state D:/workshop/oct/aig-flow-state/.artifacts/phase2-20261011/real-release-state --mcp-url https://certain-validity-bars-courts.trycloudflare.com/mcp
$env:SAFEOPS_REAL_E2E = '1'
& $phase2Python -m scripts.phase2_live_check --state D:/workshop/oct/aig-flow-state/.artifacts/phase2-20261011/real-release-state --public-url https://certain-validity-bars-courts.trycloudflare.com/mcp --output D:/workshop/oct/aig-flow-state/.artifacts/phase2-20261011/real-platform-attempt-1
& $phase2Python -m scripts.phase2_live_check --state D:/workshop/oct/aig-flow-state/.artifacts/phase2-20261011/real-release-state --public-url https://certain-validity-bars-courts.trycloudflare.com/mcp --output D:/workshop/oct/aig-flow-state/.artifacts/phase2-20261011/real-platform-attempt-2 --resume-run 1946a97b-29d6-4307-9664-a2aba7517add --prior-denial D:/workshop/oct/aig-flow-state/.artifacts/phase2-20261011/real-platform-attempt-1/real-evidence.json
~~~

Preflight **PASS**. Both qualification runners exited **1** conservatively: first
early browser wait, second actual Unknown. Across them: one generated Plan, one
denied canary, one real write-path invoke; no repeated side effect. Non-dry-run CLI
registration ran once in an isolated child process with private environment
credentials and generated reference-only config.

Final secret/preservation scan covers public tracked/untracked files, actual private
credential/key/capability matches in memory, generic secret patterns, protected
baseline, installed core equality and unchanged HEAD: **PASS**, zero secret findings.
Evidence: preservation-secret-scan.json.

## H. Remaining external blockers

1. Proxy forwarding returned no verifiable result/receipt. Diagnose the retained
   platform Plan/routing/audit read-only; do not retry Unknown.
2. Dashboard connectivity is absent; SDK API keys receive 401 on policy detail and
   Plan/audit-related dashboard APIs. Active policy/explicit deny and remote audit
   remain unverified. Registration and genuine denial occurred; approval is not pending.
3. A continuing demo needs a supported public endpoint. Temporary test connectivity
   is retired; no permanent deployment was authorized/performed.

## I. Submission

[Copy-ready submission draft](submission.md), [2–3 minute script](demo-script.md),
locked reproduction and this report are prepared. No demo video/upload, fabricated
audit link, Phase 2 commit link, event registration request or final submission.
A real matching receipt/audit and organizer submission rules/destination remain required.

Verified 11 October against the [official Flow State page](https://armoriq.ai/hackathons/flow-state)
and linked [Luma registration](https://luma.com/tttqkw24): online **10–17 October 2026**,
submissions close **17 October**, UTC on the landing page. Exact closing hour/final
submission form were unavailable in retrieved content. Luma lists solo/teams up to
four and host approval. Do not assume Auckland midnight. Final video, qualified
evidence and organizer deadline/form require completion. Phase 2 commit/push and
final submission require separate explicit authorization.

## J. Verification gates

Reachability PASS refers to the actual temporary test window. Browser PASS means
local complete browser regression and real Unknown preservation, not cloud success.
Submission package PASS means truthful draft/script prepared; readiness remains NO.
NO_DOUBLE_EXECUTION verifies one dispatch/no consumer double write, not remote exactly-once.

~~~text
BRAND_AEGIS_RELAY=PASS
EXISTING_IDENTIFIERS_PRESERVED=YES
CORE_RUNTIME_UNCHANGED=YES
CORE_DEPENDENCY_PINNED=PASS
ARMORIQ_SDK_0610=PASS
ARMORIQ_AUTH=PASS
PHASE1_REGRESSION=PASS
MOCK_MODE_E2E=PASS
LIVE_MODE_IMPLEMENTED=PASS
MCP_PROTOCOL=PASS
MCP_REACHABILITY=PASS
REAL_AGENT_REGISTRATION=PASS
REAL_POLICY_ASSIGNMENT=BLOCKED
REAL_ALLOWED_INVOCATION=BLOCKED
REAL_POLICY_DENIAL=PASS
ONE_DURABLE_EFFECT=BLOCKED
NO_FORBIDDEN_EFFECT=PASS
NO_DOUBLE_EXECUTION=PASS
UNKNOWN_HANDLING=PASS
BROWSER_E2E=PASS
RESTART_RECOVERY=PASS
SECRET_SCAN=PASS
DOCUMENTATION=PASS
SUBMISSION_PACKAGE=PASS
PHASE2_REAL_E2E=BLOCKED
READY_TO_SUBMIT=NO
ACTUALLY_SUBMITTED=NO
~~~
