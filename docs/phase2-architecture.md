# Phase 2 architecture decision

Decision: **A — ArmorIQ proxy forwards to a separately served protected MCP**.
The MCP alone calls `HandoffStore.persist`; the operator executor verifies its
receipt against the existing business store. It never writes a second handoff.
No enforce-only path is assumed. The frozen core still registers exactly one tool.

Inspected installed `armoriq-sdk==0.6.10`, Python 3.13, 11 October 2026:

- `ArmorIQClient(..., api_key=None, agent_id=None, user_id=None, timeout=30,
  max_retries=3, mcp_credentials=None, ...)` resolves existing CLI credentials.
- `capture_plan(llm, prompt, plan, metadata=None)` constructs `PlanCapture` locally.
- `get_intent_token(plan_capture, policy=None, validity_seconds=60)` calls
  `/iap/sdk/token`. Its implementation overrides the HTTP timeout to 30 seconds.
- `invoke(mcp, action, intent_token, params=None, merkle_proof=None, user_email=None)`
  posts once to the proxy `/invoke`; this **executes** the forwarded tool.
  `MCPInvocationResult` has `result`, `status`, `execution_time`, `verified`,
  `metadata`, not the `data` / `duration_ms` fields shown in some documentation.
- `max_retries=0`; no `invoke_with_policy` or hold/retry/delegation loop.
- SDK constructor health probing tolerates outages. It is not authentication proof.
- CLI `register --dry-run` skips cloud registration but still writes local state
  and logs and prints misleading “registered” text. Run it with isolated USERPROFILE.
- `bootstrap()` caches its result. Use `refresh_bootstrap()` or a new SDK client
  to verify registration after a mutation; a cached pre-registration response is stale.
- YAML URL and identity fields are not generally interpolated by the installed
  parser; only explicitly implemented API-key and MCP credential resolution is used.

Evidence sources: installed `client.py` (103–245, 551–611, 727–960), `models.py`
(57–96), `cli.py` (199–278, 443–511), `config.py` (38–175), and the
[Python SDK](https://docs.armoriq.ai/platform/sdk-cli/python-sdk),
[MCP format](https://docs.armoriq.ai/sdk/mcp-directory/mcp-format/index), and
[policy enforcement](https://docs.armoriq.ai/platform/policies/enforcement) docs.
Unmatched policies can allow by default: an explicit active canary deny must be
assigned to the actual agent/MCP target and demonstrated live.

## Dispatch and effect ownership

The existing authenticated execution route records an Action ID hint using the
public `Runtime.actions.get` API. This hint grants nothing. Inside the registered
executor, after the core claims the Action, the permit issuer re-reads that Action,
requires `Executing` with independent authorization, and compares its compiled
ExecutionSpec and effect key exactly. No consumer writes the core database.
The permit binds action/run/authorization/attempt IDs, effect, full binding,
store identity, payload digest, service ID, issuance and a short expiry. Ed25519
signatures are verified by the MCP with its public key. A random effect UUID or
MCP bearer alone cannot authorize a write.

Three reviewed business arguments plus the signed backend `_dispatch` envelope
are captured as one ArmorIQ step and passed unchanged to `invoke`. No model call
occurs at execution. The MCP uses closed schemas, a separate service bearer,
bounded requests, and independent signature/scope/digest checks. Its canary is
permanently nondestructive even if the external policy accidentally allows it.
The existing business SQLite identity/schema and duplicate/conflict behavior are
reused unchanged. Separate private live configuration and audit storage are
explicitly provisioned; startup never creates keys or migrates existing state.

Receipt success requires matching effect/scope/binding/digest/store/action and
UUID receipt, then a matching persisted business record. HTTP success or the
SDK `verified` boolean alone is insufficient. Missing/malformed/lost responses
remain Unknown. Explicit proxy block/hold and pre-invocation token failures
prove no forwarding and use the core's supported INPUT_REJECTED failure reason;
consumer audit retains the distinct failure class.

The frozen core's tool budget is five seconds. A dispatch expires before that
budget, and the worker rechecks it before invoking. A late token request cannot
start a fresh dispatch. A forwarded request can outlive acknowledgement: core
Unknown is retained without retry or automatic reconciliation. No distributed
exactly-once guarantee is claimed.

Deployment is a same-host MCP sharing the business store with the loopback UI;
the service loads the verification key and bearer, not the operator capability
or signing key. Same-user host compromise is outside this demo's trust boundary.
Public HTTPS forwarding must expose only the separate MCP port and requires
operator approval. Cloud registration and policy changes also require approval.
The operator approved this specific limited test on 11 October 2026. See the report
for actual registration, denial, Unknown execution and browser/API audit blockers.
