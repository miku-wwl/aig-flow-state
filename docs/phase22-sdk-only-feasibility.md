# Phase 2.2 — SDK-only feasibility spike

Measured 11 October 2026 UTC / 12 October NZDT against the real production API,
using installed `armoriq-sdk==0.6.10`, existing organization credentials and
synthetic data. **Remote tool policy enforcement works; the complete SDK-only
execution architecture remains BLOCKED. No application refactor is justified yet.**

| Requested result | Status and evidence |
| --- | --- |
| SDK_ONLY_REMOTE_ALLOW | **PASS — remote policy permission.** HTTP 200 `/iap/sdk/enforce`, explicit Allow, correct handoff message and matched policy ID/name. Both ordinary SDK and exact Core/permit requests verified. |
| SDK_ONLY_REMOTE_DENY | **PASS.** Canary returns explicit Block, `tool_not_in_allowlist` and the same policy ID/name. A separate request with `policy_snapshot=null` also denies. No local evaluator or mock. |
| POLICY_BINDING | **BLOCKED remotely; PASS locally.** Remote enforcement also allows changed arguments and a forged permit. Response lacks Action/Plan/digest/signature/target binding. Local gates reject wrong target/scope/adapter, changed arguments and forged signature. |
| REMOTE_AUDIT | **BLOCKED.** Request IDs and hashes retained, no persistent audit ID returned. Organization trace GET returns 401; no connected browser. Correlation does not prove persisted audit. |
| EXPECTED_EXECUTION_LATENCY | **PARTIAL.** Six real checks: 740–853 ms. Initial token + check: 3,007 ms. Core-bound token + check: 4,022 ms; no-write gateway: 4,333 ms. Business commit/receipt NOT RUN; no percentile guarantee. |
| CORE_BUDGET_COMPATIBILITY | **BLOCKED.** Probe fits frozen 5 seconds, but existing 4-second permit expires before dispatch. No successful business execution/receipt. SDK token/enforce/report timeouts remain 30/10/5 seconds. |
| COMPETITION_ACCEPTABILITY | **PASS for integration choice.** [Official FAQ](https://armoriq.ai/hackathons/flow-state) permits SDK integration without an MCP server. Project execution/audit qualification and submission readiness remain blocked. |
| RECOMMENDED_ARCHITECTURE | **NO-GO for changes now.** Preserve the application. Resolve remote exact binding, audit verification and permit/budget qualification before choosing an execution architecture. No implementation change proposed or made. |

Installed implementation: `start_plan` builds/captures steps and requests a token;
SDK-mode `check` calls backend `enforce_sdk`, never business `/invoke`.
`EnforceResult` drops policy ID/correlation; enforcement interprets JSON without
checking HTTP status. This spike separately checks HTTP 200 and raw policy ID.
`report` posts `/iap/audit`, returns `None`, ignores HTTP status and increments the
step counter even on failure. **Report NOT RUN:** no business execution occurred.

Fresh context links policy `c4b4d803-aefd-4c74-bc0c-dbb4564d399c`
(`cli-aegis-relay-aegis-relay-mcp`) to MCP `0b4133a0-9acd-451b-84a2-a795d9c593c5`.
Enforcement identifies the policy; target association requires this separate read.
Before/after inventories match.
Allow request IDs: `ce2c1d6e-9446-4cd9-b1ca-e3a967ac4de5` (ordinary),
`98be96fc-0c99-4e7f-aecc-f069cce96014` (Core-bound).
Deny: `a1d37130-5f82-4e91-a752-6f58c9172f59`; without client snapshot:
`7850a454-dcc8-4258-b80a-49497cde1523`. These are server request IDs, not audit IDs.

Independent verification is **BLOCKED**: `/iap/public-key` returns HTTP 200,
`enabled=false`, null key/JWK. The JWT declares HS256; SDK EdDSA verification is
unavailable. `client.verify_token` also returns false; its cause is not asserted.

The isolated Core probe used the pinned installed runtime
`fd742b783058a53400c465b4ab59c6e80715895a`: validated Plan → persistent Run → exact
Approval → separate Authorization → durable claim → permit issuance → remote check.
Its **no-write executor refused business execution**: fresh Action Failed, zero
handoffs. This is not business success. Local negatives ran before permit expiry;
remote negatives never dispatched tools.

Private evidence in `.artifacts/phase22-20261012/`: `installed-api.json`,
`remote-initial.json`, `binding-results.json`, `final-evidence.json`,
`verification.json` and probe scripts. Raw keys/JWTs/permits were not persisted;
telemetry was disabled. [Official audit-read documentation](https://docs.armoriq.ai/platform/observability/api-reference)
requires Bearer JWT for organization GET routes.

All 4,337 readable protected files retain their hashes; one locked owner file retains
metadata. Original Unknown's 22 evidence files, tracked sources and installed
Core/SDK files are unchanged. No existing Action was opened/retried/modified, no
business/MCP invocation, registration/policy mutation, deployment, core edit,
commit or push. Full application tests NOT RUN: application code is unchanged.
