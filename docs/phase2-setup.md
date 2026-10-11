# Phase 2 operator setup

**Current Phase 2.1 status: local protocol/auth PASS; real E2E BLOCKED.** The
operator has no configured stable endpoint and declines DNS/named-tunnel setup.
No deployment or public exposure is approved for Phase 2.1. Complete local work
and choose the next route using [the diagnosis](phase2-blocker-diagnosis.md).

The operator approved the limited temporary tunnel, project registration/policy and
synthetic real tests on 11 October 2026. These tests ran; see the
[current report](phase2-e2e-report.md). Full qualification remains blocked because
the handoff ended Unknown and dashboard policy/audit evidence is unavailable.
Existing `.runtime/local` is preserved. Do not rerun `init` over existing state.
Default enforcement remains `mock`; `real` never falls back to mock.

## Private preparation

```powershell
uv sync --locked
uv run safeops init --state .runtime/phase21-review
uv run safeops init-live --state .runtime/phase21-review
uv run safeops mcp --state .runtime/phase21-review --port 8766 --diagnostics
```

The two initialization commands are exclusive and explicit. `init-live` adds
Ed25519 dispatch keys, a separate 256-bit MCP bearer, service identity and live
audit database, without changing business/core schemas. Keep this entire state
private. The MCP reads only its public verification key and service bearer;
it exposes only POST `/mcp`, no operator UI, capabilities or database downloads.
The loopback operator UI remains on its own port. One core owner/worker, no reload.

Use the existing logged-in CLI credentials; do not log in again, create a key,
switch organizations, or print the credential file. Real SDK credentials are
read in memory. `ARMORIQ_API_KEY` and `SAFEOPS_ARMORIQ_USER_EMAIL` are optional
operator-managed overrides. No credentials belong in source or screenshots.
The adapter pins HTTPS SDK endpoints from installed 0.6.10's production table,
enables TLS verification, disables redirects and sets `max_retries=0`.
YAML `environment: sandbox` is a registration field; it is not proof of isolated
infrastructure or a separate sandbox API host.

With the protected MCP running, from the repository root:

```powershell
uv run python -m scripts.armoriq_preflight --state .runtime/phase21-review
uv run python -m scripts.diagnose_mcp_discovery --state .runtime/phase21-review --url http://127.0.0.1:8766/mcp --cli --output .artifacts/phase21-review/local-discovery.json
```

This performs authenticated SDK bootstrap, actual CLI validation, and an actual
dry-run in an isolated child USERPROFILE. It writes a credential-reference-only
`registration-review.yaml` and sanitized `preflight.json` under private state.
The SDK 0.6.10 CLI dry-run still writes local status/log files and prints
“registered”; these outputs do **not** prove platform registration. The actual
operator's CLI profile is preserved. Do not use `ArmorIQClient.from_config` as
an execution boundary: the application owns capture, dispatch and receipt checks.

## Historical approval scope — completed, not a new deployment instruction

The following scope was approved for this run. For a separate deployment, review
[the architecture](phase2-architecture.md) and obtain that operator's authorization:

1. A free temporary HTTPS tunnel forwarded **only** `127.0.0.1:8766` to the
   protected MCP. Download a pinned official Cloudflare cloudflared binary into
   ignored D: artifacts if necessary; verify its published SHA256. No UI tunnel.
   That Quick Tunnel is retired; do not create another for final qualification.
   The endpoint uses a separate bearer and signed dispatch; the canary cannot delete.
2. Register or update only agent `aegis-relay`, MCP `aegis-relay-mcp`, and its
   narrow policy allowing `create_incident_handoff` and explicitly denying
   `purge_incident_history`, in the existing organization. Inspect existing names
   and resource IDs first. No duplicate resources, global policy changes or new keys.
3. Two synthetic intent paths: one reviewed authorized write and one separately
   captured canary deny. No production incident systems, paid services or submission.

Cloudflare's [Quick Tunnel documentation](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
explicitly excludes SSE support. This MCP returns one finite SSE event with a closed
response, rather than a persistent event stream. Public initialize/tools-list and
installed CLI discovery worked over the temporary tunnel in this run; this proves
that limited discovery path, not general SSE support or successful ArmorIQ forwarding.
Use a supported stable endpoint for the current proxy architecture. The operator
has now declined DNS and named Cloudflare Tunnel configuration.
The downloaded official Windows amd64 cloudflared 2026.10.0 was verified against
published SHA256 `86aee4017b26625cee8484c113558f48effa4cd47f7aa05fcf425604e5d2b23c`.
The temporary tunnel is stopped after testing. Cloud project registrations and their
policy remain; they have not been deleted or broadened.

The checked-in `armoriq.yaml` matches the actual 0.6.10 schema and currently has
a local review URL. Replace it only in the private generated review config with
the approved HTTPS `/mcp` URL. Run preflight against that endpoint. Load API key
and MCP bearer privately into child-process environment variables; never print
them or put resolved values in YAML. Only after approval run actual registration.
Verify resource names/IDs, active target-bound policy and credential forwarding
on the dashboard. The installed CLI sends environment references in its register
payload; do not assume the control plane resolves an operator's local variables.
The SDK supplies the actual per-MCP credential in the invocation's protected
`X-Armoriq-MCP-Auth` header. Validate discovery and forwarding before the live demo.
If the platform requires a resolved service credential for registration, send it
only through an approved authenticated platform request, never source/logs/config.

The policy CLI `armoriq policy` edits an organization-wide profile; **do not use
it for this resource-specific qualification**. Use the agent/MCP assignment UI
or a verified target-specific API. Unmatched rules may allow by default, so
an explicit active deny assignment and a real denial result are mandatory.
Actual SDK CLI registration created a project-targeted policy with an allowed-tools
whitelist and default block. The separate real canary was denied. Its active status
and explicit deny representation still need dashboard verification; do not equate
CLI “Policy applied” output with that proof. Platform tool inventory was empty even
though direct authenticated public MCP discovery found both tools.

## Real operator UI and opt-in qualification

Run this section only after current local/external authentication and SSE, cloud
discovery/routing, existing IDs, active target policy, receipt checks and budget
assessment pass, and the operator authorizes the fresh trial. These gates are
currently BLOCKED; the commands below have **not** been run in Phase 2.1.

```powershell
uv run safeops serve --state .runtime/phase2-release --provider ollama --enforcement-mode real --port 8775 --predecessor-stopped
```

The live badge indicates selected transport, not qualification success. Connectivity
starts NOT_PROBED; registration remains UNVERIFIED until separately evidenced.
Private audit reports exact classification and action/plan/receipt correlation.
The policy lab probes only the nondestructive canary in real mode. Business writes
must pass the existing core gates. Core denial and ArmorIQ policy denial differ.

For an empty prepared state, with its separate MCP/tunnel still running and no
operator UI owner running against that state, explicitly opt in:

```powershell
$env:SAFEOPS_REAL_E2E = '1'
uv run python -m scripts.phase2_live_check --state .runtime/phase2-release --public-url https://APPROVED-HOST/mcp --output .artifacts/real-qualification-NEW
```

This intentionally performs a real headed-Chrome/Ollama workflow, explicit review
and authorization, one forwarded write, exact-request replay, separate captured
canary intent, refresh and restart. It never deploys, registers, changes policies
or submits. It fails if the state already has records; choose prepared fresh state,
never clear existing data. It saves sanitized evidence and screenshots, not tokens.
Dashboard registration/assignment and audit screenshots must be checked separately;
the script conservatively leaves the overall release gate BLOCKED until supplied.
Planning uses an explicit 35-second browser expectation, within the existing 30-second
core request behavior plus UI response time. If planning completed after an early
browser wait, `--resume-run UUID` can review an existing AwaitingApproval Run. It
refuses other states and never redispatches an Action. `--prior-denial FILE` may reuse
a real denial from this same state's durable audit without probing the canary twice.
Partial failures save the Action and audit so Unknown is not hidden by the runner.

Never run the write qualification again against this run's Unknown Action. The retained
real release state is evidence, not a disposable test database. Diagnose the platform
Plan and forwarding/audit through authenticated read-only tools first; a zero row count
does not turn Unknown into a confirmed safe retry.

Unknown means no automatic redispatch or reconciliation. The five-second frozen
core budget includes capture/token/invoke. Permit expiry blocks late new writes,
but a commit with a lost response can leave one record and an Unknown Action.
Keep that evidence. Do not promise exactly-once delivery.

## No-domain options prepared for review

The smallest researched transport change for the existing proxy architecture is
an ngrok **Free** account's assigned dev domain. It supplies stable HTTPS without
using the operator's domain or changing DNS. See [free plan limits](https://ngrok.com/docs/pricing-limits/free-plan-limits)
and the provider's [SSE compatibility statement](https://ngrok.com/compare/cloudflare-tunnel).
Verify the actual account remains on Free and has unused allocation; do not upgrade,
add billing, reserve a paid custom domain or assume credits. API clients are not
subject to its HTML warning page. An agent endpoint is online only while its host
and the protected MCP are running.

Prepared configuration, **not deployed**:

- Public address: the actual assigned `https://<DEV-DOMAIN>/mcp`.
- Upstream: only `http://127.0.0.1:8766`; no 8765/8775/UI or filesystem forwarding.
- Service: existing protected MCP with Bearer plus signed permit mandatory.
- Private state: a new exclusively provisioned review directory, never old Unknown state.
- Credentials: operator installs/configures the official agent privately; no authtoken
  in commands, source, generated public YAML, screenshots or tool output.
- Traffic capture/replay: keep cloud Full Capture off and disable local request
  inspection in the selected agent; use the application's sanitized diagnostics.
  Never use a tunnel inspector to replay a tools/call.

After explicit approval, the concrete endpoint command is:

```powershell
# The agent must already have private account authentication configured.
ngrok http http://127.0.0.1:8766 --url https://ACTUAL-ASSIGNED-DEV-DOMAIN --inspect=false
```

Verify those flags against the selected agent version before launch. No agent was
installed or launched by this task. No hostname/account allocation is invented.
Stop the agent with Ctrl+C when qualification ends. Do not reuse Quick Tunnel.

After publication is approved and running, test independently before any mutation:

```powershell
uv run python -m scripts.diagnose_mcp_discovery --state .runtime/phase21-review --url https://ACTUAL-ASSIGNED-DEV-DOMAIN/mcp --external --cli --output .artifacts/phase21-review/external-discovery.json
$env:SAFEOPS_ARMORIQ_READONLY = '1'
uv run python -m scripts.diagnose_mcp_discovery --state .runtime/phase21-review --url https://ACTUAL-ASSIGNED-DEV-DOMAIN/mcp --external --cloud --output .artifacts/phase21-review/cloud-inventory.json
```

The script sends initialize, initialized and tools/list only, with a 64 KiB response
limit, short HTTP timeout and no redirects. Cloud reads refresh supported bootstrap,
inventory, schemas and user context; they do not discover by forwarding a tool.
CLI discovery is a separate optional local/client probe. Only after actual CLI
validate and operator-approved resource upsert, verify the original agent/MCP IDs,
registered URL/auth, actual cloud tool count, active policy and incoming auth scheme.
Do not rerun registration without an identified change. The unresolved credential
reference behavior remains a platform question; never disable auth or write secrets
to a registration YAML to force a scan to pass.

Alternatively, official SDK-only enforcement can request a real cloud policy
decision without exposing the MCP. Installed 0.6.10 implements `start_session`,
`SessionOptions(mode="sdk")`, `start_plan`, `check`/`enforce_sdk` and `report`.
It does not forward the business tool. A reviewed small consumer change would keep
the same signed, authenticated loopback MCP as sole writer, require explicit Allow,
verify its receipt and then verify remote audit. This route was researched only;
it requires a separate architecture/competition/budget review, not a silent fallback
from LIVE proxy to local execution. See [the SDK-only assessment](phase2-blocker-diagnosis.md#h-minimal-next-steps-without-a-domain).

Free Render hosting is unsuitable for the unchanged durable SQLite design: local
files disappear on restart/spin-down and persistent disks require a paid service.
No hosting account, resource or deployment was created. Microsoft persistent Dev
Tunnels and Tailscale Funnel remain alternative candidates requiring setup and
actual authenticated SSE/cloud checks, rather than assumed compatibility.

## Safe source packaging

The existing `D:/workshop/oct/aig-flow-state.zip` is a private workspace snapshot
containing runtime state and keys. Do not upload it. Keep it for private evidence;
this task did not overwrite it. The explicit sdist inclusion list excludes private
state, environments and caches. Build with `uv build --sdist --out-dir <NEW-OUTPUT>`
and inspect members/secrets before distribution. A public source ZIP must be made
from the public Git file inventory, not a recursive workspace archive. Neither
the old Unknown database nor any other runtime state belongs in a public package.
