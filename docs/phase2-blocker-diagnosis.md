# Phase 2.1 diagnosis — 12 October 2026 NZDT

**PHASE2_REAL_E2E=BLOCKED · READY_TO_SUBMIT=NO · ACTUALLY_SUBMITTED=NO**

Measurements were taken on 11 October UTC / 12 October Auckland. The old real
Unknown Action was inspected through read-only SQLite connections, never opened
in a runtime composition. No new real Action, token, proxy invocation, canary,
cloud mutation, public endpoint, DNS change, deployment or submission occurred.
Current CLI credentials were used only for authenticated inventory reads.

## A. Evidence and causes

| Blocker | Evidence | Proven cause / correction | Remaining uncertainty |
| --- | --- | --- | --- |
| Malformed service authentication | Before: a non-ASCII header caused HTTP 500. After: missing, wrong, non-ASCII and duplicate headers return 401. | String `compare_digest` rejects non-ASCII input. Compare encoded bytes while retaining the exact single trusted Bearer requirement. Fixed. | No evidence this caused the old cloud failure. |
| Protocol negotiation | Before: unknown initialize version produced RPC error; unsupported HTTP version header produced tools. | Negotiate to the latest supported version when initialize proposes another version; reject unsupported/duplicate HTTP protocol headers with 400. Fixed. | Cloud's actual requested version was not retained. |
| Invalid request identity | Invalid array IDs were echoed in errors; a tool request with null/missing ID could reach dispatch verification. | Validate IDs before retaining them; tool requests require an ID. Fixed without weakening permit checks. | No evidence these requests occurred remotely. |
| Retired public transport | Fresh `list_mcps` still identifies a trycloudflare endpoint. Its host/process were stopped after Phase 2. | The registered endpoint is currently offline. Quick Tunnel is temporary and officially excludes SSE. A replacement is required for the existing proxy architecture. | Earlier finite public SSE discovery succeeded; this does not prove Quick Tunnel caused the original Unknown. No replacement deployed. |
| Cloud has zero tools | Fresh bootstrap, tool schemas and tool map all contain zero tools; local parser and installed CLI discover two. | Cloud inventory remains unqualified. CLI local discovery and registration are separate operations. | Initial probe auth, cloud parsing, registration credential handling and scan failure reason require platform evidence. |
| OAuth / Bearer discrepancy | User reports Dashboard OAuth 2.0; local YAML/server and actual SDK invocation configuration use Bearer. | CLI 0.6.10 sends an auth block whose token is still `$SAFEOPS_MCP_BEARER`; local discovery resolves it independently. Actual SDK `/invoke` sends the resolved credential through `X-Armoriq-MCP-Auth`. | SDK inventory exposes no auth method/credential state. UI default versus actual wrong metadata, and credentials arriving from the cloud, remain UNVERIFIED. |
| Policy card versus SDK context | Fresh SDK context still targets the original MCP with handoff whitelist, priority 100 and default block. | Policy existence and SDK target association are verified; a dash on a card is insufficient proof of absence. | Enabled/active status and explicit canary override are not returned. Actual Allow enforcement and Dashboard association remain BLOCKED. |
| Original Unknown | One retained attempt; IAP Plan ID exists; consumer audit says UNAVAILABLE; no receipt and zero rows. | Source narrows failure to the invoke stage, before a usable result/receipt. The underlying exception/status was not saved. | Cannot distinguish proxy connectivity, forwarding/auth/discovery or response propagation. Cannot prove core timeout. Do not retry or reclassify. |
| Audit access | Prior Dashboard-only API reads returned 401 under SDK credentials; current browser surface inventory is empty. | Permission/tool-connectivity boundary, not proof that remote records or policy are absent. | Authenticated Dashboard inspection remains required. |

The latest [MCP lifecycle specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle)
requires an unsupported initialize proposal to receive a supported server version;
the client then accepts that version or disconnects. Unknown versions are never
claimed as supported. The [HTTP transport specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
requires 400 for unsupported version headers and permits 405 for the optional GET
stream. ArmorIQ's [MCP format](https://docs.armoriq.ai/sdk/mcp-directory/mcp-format/index)
documents POST `/mcp` with finite SSE responses. No speculative legacy SSE adapter
or extra tool was added.

## B. Actual Phase 2.1 changes

| Files | Purpose |
| --- | --- |
| src/safeops/mcp/server.py | Fix byte authentication, negotiation, protocol header and invalid request ID handling; opt-in private diagnostics and permit/write timings. |
| src/safeops/main.py | Add MCP-only `--diagnostics`; keep loopback binding and access logs disabled. |
| src/safeops/integration/live_armoriq.py, live_audit.py | Record capture/token/proxy/receipt timings, response status/timing and closed exception classifications; existing JSON event storage, no schema migration. |
| scripts/diagnose_mcp_discovery.py | Bounded independent SSE/JSON-RPC/schema validation, explicit external/cloud opt-in, fresh supported inventory reads. Never calls a tool, issues a token or registers. |
| tests/test_mcp_diagnostics.py, tests/mcp_server_process.py | Twenty focused cases, actual SDK credential-header/payload checks over offline transport, redaction and diagnostic subprocess support. |
| pyproject.toml | Explicit source-distribution inclusion list; preserve dependencies and frozen core SHA. |
| README.md; docs/phase2-setup.md, phase2-e2e-report.md, submission.md, this file | Current results, deployment options, blockers and release gates. |

Brand Aegis Relay, safeops identifiers, trusted tool identity, authorization,
claiming, signatures, permit expiry, SQLite schemas, single writer and Unknown
behavior are preserved. The actual installed public core API and consumer example
were inspected. Remote annotated `v0.1.0` still resolves to
`fd742b783058a53400c465b4ab59c6e80715895a`; installed direct URL and lock match.

## C. Three network levels

| Path / check | Status | Observable evidence |
| --- | --- | --- |
| Loopback missing / invalid Bearer | PASS | HTTP 401, application/json; 16.922 / 4.212 ms total request time. |
| Loopback initialize | PASS | HTTP 200, text/event-stream; exact string ID, negotiated 2025-06-18; 4.442 ms. |
| Loopback initialized notification | PASS | HTTP 202, empty body; 5.212 ms. |
| Loopback tools/list | PASS | HTTP 200, text/event-stream; exact integer ID, two expected tools, valid JSON Schemas; 4.189 ms. |
| Installed CLI discovery / validate | PASS | Two tools from actual CLI discovery; actual validate and isolated dry-run passed against loopback. Dry-run is not registration. |
| Current external HTTPS | BLOCKED | No approved running stable endpoint. Earlier Quick Tunnel evidence is historical. |
| Current ArmorIQ inventory read | PASS | Four HTTP 200 application/json SDK reads, fresh client/bootstrap; combined 3448.311 ms. No tool execution. |
| ArmorIQ discovered tool qualification | FAIL | Bootstrap count 0, schema count 0, tool map count 0. No new cloud probe/rescan against a replacement endpoint. |

These are full request durations, not isolated TCP-connect measurements. Server
diagnostics record a generated correlation UUID, controlled route/method/scheme,
auth outcome, RPC outcome and timings. No Authorization value, input payload,
signature, raw token, provider body or exception message is retained. The diagnostic
script rejects response overflow, incomplete SSE, RPC errors, wrong IDs and schemas;
a plain HTTP 200 cannot pass discovery.

## D. Authentication evidence and documentation differences

Installed `config.py` stores the environment reference in `to_yaml_dict`; installed
`cli.py` registers that dictionary. A focused MockTransport test inspected the
actual registration request and proved its token remained a reference. Credentials
were not omitted as a block, but the actual local token was not substituted into
that body. The backend cannot be assumed to know this workstation's environment.
This differs from the [YAML reference's substitution description](https://docs.armoriq.ai/platform/sdk-cli/armoriq-yaml).
No installed SDK source was patched and no resolved secret was written to YAML.

An actual SDK offline invocation test separately verifies `X-API-Key` and decoded
`X-Armoriq-MCP-Auth={authType: bearer, token: <private>}`. This proves consumer
configuration, not remote credential forwarding. The documented
[manual registration wizard](https://docs.armoriq.ai/platform/mcp-servers/add-server)
offers an Auth Method field but does not establish authenticated registry discovery
behavior for this SDK payload. Inspect/update the existing resource when an approved
endpoint is running; do not add another MCP, guess an OAuth flow, or remove auth.

## E. Policy evidence

Fresh inventory identifies the existing organization
`95701a09-81a7-41d8-8d8a-58d5cb83dc27`, agent
`2a9ea47b-0261-47d4-9670-d45118d7778a`, MCP
`0b4133a0-9acd-451b-84a2-a795d9c593c5`, and policy
`c4b4d803-aefd-4c74-bc0c-dbb4564d399c`.
Policy name remains `cli-aegis-relay-aegis-relay-mcp`; target type `mcp_server` and
target ID match that MCP. Priority 100, allowed tool `create_incident_handoff`,
default action `block`. No enabled field or explicit denied-tools list is provided
by this response. Verify the active policy/member rules and the
[server detail association](https://docs.armoriq.ai/platform/mcp-servers/registry)
in the same organization. Do not edit the organization-wide CLI policy profile.

Reuse the genuine 11 October canary denial: local evidence UUID
`d1d3a52f-b60e-483a-8f50-3cd51cbe1181`, 10:10:31.570332 UTC. Its classification
required explicit policy-denial metadata, not a generic 403, mismatch or bearer
rejection. No Action or forbidden write was created. The relevant target/context
is unchanged in the fresh read. This local evidence UUID is not a remote audit ID.
It does not establish an explicit active Dashboard override. The
[platform enforcement documentation](https://docs.armoriq.ai/platform/policies/enforcement)
describes default allowance for unmatched policies/rules; do not generalize the
observed CLI whitelist's default block to every platform policy.

## F. Retained real execution and budget

Original Run `1946a97b-29d6-4307-9664-a2aba7517add`, Action
`3b1930f9-d28e-4b0d-8563-287108cbfd79`, effect
`6b3640a8-4d4f-4a8a-9e80-4fc4fbd0a5d9`, IAP Plan
`707bb43b-5159-417a-b8a7-f6895cc55b37`.

| Stage | UTC, 11 October |
| --- | --- |
| Created | 10:12:53.508404 |
| Independently authorized | 10:12:53.814321 |
| Durable claim, sole attempt | 10:12:53.969944 |
| Consumer UNAVAILABLE event | 10:12:58.357637 |
| Core Unknown, version 4 | 10:12:58.394066 |

Claim to terminal elapsed 4424.122 ms. IAP token acknowledgement precedes the invoke
stage but its exact time was not retained. No receipt verification occurred. The
old evidence does not identify HTTP status, network cause or MCP receipt of the call.
Zero rows remain an observation, not grounds for changing Unknown into Failed.

The installed core limits tool execution to **5 seconds**. YAML proxy timeout is
2 seconds and intent TTL is 10 seconds. The consumer explicitly constructs a
2-second SDK client with zero retries; installed SDK token issuance overrides that
timeout to **30 seconds**. Signed permits last at most 4 seconds and expire before
the core deadline. New dispatch is blocked after cancellation/expiry. These values
were not increased or monkeypatched.

Separate fresh **offline SDK transport** measurement: capture 0.102 ms, token
1.074 ms, entire proxy operation 25.656 ms, MCP permit verification 0.607 ms,
MCP SQLite write 9.069 ms, receipt verification 2.513 ms; total executor 48.622 ms.
Its Action Succeeded, exactly one row/receipt and one invoke; replay did not invoke.
This is not real cloud timing. The new instrumentation separates stages and HTTP
response-header duration; it cannot retrospectively recover the old connection time.
**CORE_EXECUTION_BUDGET=BLOCKED** until the selected real route is measured. There
is insufficient evidence to conclude that live execution inherently cannot fit.
Prewarm/reuse connections and verify discovery before the future trial; retain
Unknown for any ambiguous result. A longer core deadline would require separately
reviewed core work; no background execution or token prefetch that changes binding.

## G. Verification and artifacts

Executed with isolated Python 3.13.9 at
`.artifacts/phase2-20261011/venv/Scripts/python.exe`:

```powershell
# Focused correction tests
python -m pytest tests/test_mcp_diagnostics.py -q --basetemp=.artifacts/phase21-20261011/focused-fix-state --junitxml=.artifacts/phase21-20261011/focused-fix.xml
# Entire current offline suite, including actual Chrome
python -m pytest -q --basetemp=.artifacts/phase21-20261011/full-state --junitxml=.artifacts/phase21-20261011/full.xml
ruff check
ruff format --check
uv lock --check
node --check src/safeops/api/static/app.js
git diff --check
```

Focused: **20 passed**. Full: **128 passed in 232.27 seconds**, including **11 Chrome
tests** and all prior **108 cases**; one existing Starlette/httpx deprecation warning.
Lint, format, locked dependency and JS checks pass. Default tests use offline SDK
transport, not the real platform. Required wrong binding/target/scope, missing
authorization, stale approval, unknown tool, forged/expired permit, receipt mismatch,
duplicate/conflict, timeout/Unknown, no redispatch, restart and browser cases remain.

Read-only real inventory and actual loopback protocol/CLI evidence are saved under
ignored `.artifacts/phase21-20261011/`: `local-before.json`, `loopback-cloud.json`,
`cli-validation.json`, `old-timeline.json`, `offline-budget.json`, test XML and private
MCP diagnostics. Original evidence is retained separately.

The prior `D:/workshop/oct/aig-flow-state.zip` contains `.runtime` and `.artifacts`,
including operator capabilities, MCP bearers and Ed25519 private dispatch keys. It
must not be distributed as public source. It was inspected, not modified/deleted.
No private-state paths/ZIP/.env are tracked or found in accessible local Git history.
A bounded archive scan did not find the current ArmorIQ API-key bytes; this does
not prove that every older credential is absent. Publication is **UNVERIFIED**;
no compromise is asserted. If the ZIP was published, revoke/replace the specific
included operator capabilities, service bearers and dispatch keys in **new** state,
preserving historical databases; rotate an ArmorIQ API key only if its inclusion
or separate exposure is established. No rotation was performed.

Source distributions now have an explicit inclusion list. Build public source from
that list/Git's public file inventory, never by recursively zipping this workspace.
Archive member names and actual local credential bytes must be checked before release.

## H. Minimal next steps, without a domain

The operator explicitly declines DNS/named Cloudflare Tunnel work and has not
approved another publication. See [the prepared setup options](phase2-setup.md).

The [official session documentation](https://docs.armoriq.ai/sdk/sessions) search
result describes SDK-only decisions. The direct page currently returns 404; the
installed 0.6.10 source confirms `SessionOptions(mode="sdk")`, `start_plan`,
`check`/`enforce_sdk`, and `report`. `check` calls `/iap/sdk/enforce`, while proxy
mode uses `/invoke` with `enforce_only=true`. Both make policy decisions;
SDK-only does not perform a forwarded business write. `report` is best-effort and
its return is not confirmed audit evidence. SDK enforcement overrides timeout to
10 seconds and reporting to 5 seconds.

A small separately reviewed SDK-only variant could keep every core gate and the
same protected **loopback** MCP as sole writer: exact signed step → cloud explicit
Allow → one authenticated local MCP call → matching durable receipt → remote audit
verification. It would avoid public hosting but change the current proxy execution
path and qualification definition. It was researched, not silently substituted or
called live. Verify competition acceptance and budget first; never use local-mode
policy decisions or an ignored `allowed` flag as real platform evidence.

For the current proxy path, the simplest researched candidate is a free ngrok
account's assigned stable HTTPS dev subdomain and one agent forwarding only 8766.
Its [official comparison](https://ngrok.com/compare/cloudflare-tunnel) explicitly
states SSE pass-through. The [free plan](https://ngrok.com/docs/pricing-limits/free-plan-limits)
includes the assigned domain and HTTPS; machine API traffic avoids the HTML warning.
Confirm remaining free allocation in the actual account; no paid upgrade or assumed
credits. Microsoft persistent Dev Tunnels and Tailscale Funnel are alternatives
requiring account/host setup and real transport verification. Free Render hosting
has an [ephemeral filesystem](https://render.com/docs/free), cold starts and no free
persistent disk, so it does not preserve this SQLite-based architecture as-is.

After a transport/variant is chosen: approve its concrete exposure or execution
scope, verify discovery/auth, inspect existing target policy and audit in a connected
Dashboard, assess budget, then authorize the one fresh synthetic trial. No organizer
message was sent; the following reproduction is copy-ready if separately approved:

> Python SDK/CLI 0.6.10: protected POST /mcp returns correctly framed SSE, matching
> JSON-RPC IDs and two valid tools to independent and CLI clients. Original public
> direct discovery found two tools, while refreshed platform bootstrap/tool schemas
> returned zero. CLI registration serializes a Bearer environment reference rather
> than its resolved local value; invocation supplies a separate resolved MCP-auth
> header. Dashboard auth is reported as OAuth 2.0. What supported mechanism supplies
> Bearer credentials to registry discovery and updates the existing MCP auth state?

Video recording/upload, source publication, organizer communication and final
submission remain separate operator actions. No permission request was made for
deployment during this qualification because the operator requested preparation only.

## I. Release decision

Local corrections and offline safety qualify. Real cloud tool inventory, remote
auth mapping, active explicit policy association, budget, new allowed effect/receipt
and remote audit do not. **PHASE2_REAL_E2E=BLOCKED, READY_TO_SUBMIT=NO,
ACTUALLY_SUBMITTED=NO**. Full gates are in [the execution report](phase2-e2e-report.md).
