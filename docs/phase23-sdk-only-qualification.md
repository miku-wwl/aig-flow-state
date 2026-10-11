# Phase 2.3 — SDK-only execution qualification

Measured 11 October 2026 UTC / 12 October NZDT, using installed
`armoriq-sdk==0.6.10` and frozen Agentic Intent Gate `v0.1.0`, release commit
`fd742b783058a53400c465b4ab59c6e80715895a` (release tag and installed Git origin
verified). **Execution qualification PASS; complete qualification PARTIAL because
independent remote audit persistence verification is BLOCKED.**

| Result | Actual evidence |
| --- | --- |
| PRE_STAGING | **PASS.** Exact Core Approval and independent Authorization precede `start_plan`. Action remains Authorized, with zero effects, until Core claims execution. One fresh session and token per Action; no refresh/retry. |
| POLICY_BINDING | **PASS locally; remote decision is tool-level only.** Immutable stage includes reviewed Run, compiled Plan/spec identities, approval decision/version, authorization, Action/effect IDs, exact arguments, trusted binding/scope, store and policy identities. Token and captured Plan are checked before and after enforcement. Remote Allow does not establish parameter or permit integrity. |
| SDK_ONLY_REMOTE_ALLOW | **PASS.** Two real HTTPS `/iap/sdk/enforce` calls, HTTP 200, explicit Allow and expected policy ID/name; actual outbound requests checked. No local evaluator or mock in these runs. |
| SDK_ONLY_REMOTE_DENY | **NOT RUN again live in Phase 2.3.** Preserve the real Phase 2.2 canary denial evidence. Focused OFFLINE tests confirm deny/hold/unavailable responses cannot reach business persistence. |
| NO_WRITE_EXECUTION | **PASS.** Full policy/context/late-permit path, 1,087.903 ms gateway time, zero business calls/records. Core terminal Failed is the probe's explicit no-effect refusal, not a successful handoff. |
| SYNTHETIC_BUSINESS_WRITE | **PASS.** One task-authorized fresh synthetic `INC-23001` write, one durable record, matching receipt, Core Succeeded. Closed-runtime, read-only SQLite verification confirms one attempt and exact approval/authorization/spec links. |
| LATE_DISPATCH_PERMIT | **PASS.** Existing Ed25519 permit issued after remote Allow, verified against exact arguments and current Executing Action/attempt. Core deadline and permit expiry checked again before write and throughout durable persistence. No expiry extension or bypass. |
| SDK_LIFECYCLE | **PASS for server acknowledgements.** `start_plan → check → local execution → report → complete_plan`. Success report and completion each HTTP 200; completion response `success=true` with matching Plan ID. Reporting happens after Core Succeeded, outside its execution budget. |
| REMOTE_AUDIT | **BLOCKED for independent persistence readback.** Report returns audit ID `b766e35d-9810-4095-9986-66989d1e907e`, but authenticated organization trace GET returns 401. No organization JWT or connected browser is available. Audit ID/POST acknowledgement is not independent persistence proof. |
| CORE_BUDGET_COMPATIBILITY | **PASS for the two measured executions.** Business gateway 1,106.662 ms; persisted claim-to-terminal 1,063.968 ms, below frozen 5 seconds. This small sample is not a latency percentile or availability guarantee. |
| MODES_AND_PRESERVATION | **PASS.** Existing MOCK and LIVE proxy application paths untouched. SDK-only adapter is separately composed through the public Core API; no fallback, deployment, public MCP, domain/DNS, registry/policy mutation, Core edit, commit or push. |
| REGRESSION | **PASS.** 24 focused tests; full consumer suite 152 passed, including existing browser/MOCK/LIVE coverage. Ruff check and format check pass. |
| COMPETITION_ACCEPTABILITY | **PASS for integration choice.** The [official FAQ](https://armoriq.ai/hackathons/flow-state) allows SDK integration and does not require building an MCP server. Submission readiness is not established by this spike. |
| RECOMMENDED_ARCHITECTURE | Keep the frozen Core as sole approval, authorization, claim and outcome authority. Prestage remotely after exact authorization; enforce remotely inside Core execution; locally revalidate and sign late; verify durable receipt; report after terminal success. Resolve audit readback before presenting the integration as fully qualified. App/UI wiring remains a separate change. |

The independent adapter is [sdk_only.py](../src/safeops/integration/sdk_only.py);
[focused tests](../tests/test_sdk_only.py) use the actual installed SDK with an
explicitly OFFLINE transport. Real qualification uses existing credentials,
verified TLS, pinned endpoints and `max_retries=0`. Request hooks reject unrelated
routes, including delegation creation. Enforcement HTTP timeouts are bounded by
the remaining Core budget; Core's unchanged deadline cancels the awaiting task.
The worker thread performs policy checks only, so a late response cannot write.
Tokens stay in memory; this spike adds no restart/resume mechanism.

The task-authorized harness recorded the exact deterministic Core Approval and
separate Authorization. It does not claim an interactive UI approval click.
Reviewed synthetic arguments were:

```json
{"incident_id":"INC-23001","summary":"Synthetic Phase 2.3 SDK-only qualification","handoff_note":"Synthetic test only; no operational incident or external recipient."}
```

| Timing (ms) | No-write | One business write |
| --- | ---: | ---: |
| Prestage total, outside Core execution | 2,423.737 | 2,184.183 |
| SDK remote enforcement | 793.872 | 851.300 |
| Durable business write | NOT RUN | 7.451 |
| Executor total, including validation/permit/receipt | 958.298 | 1,024.493 |
| Persisted Core claim → terminal | 1,019.990 | 1,063.968 |
| Gateway total | 1,087.903 | 1,106.662 |

Business Action: `44018e15-1500-42e2-816e-81470ffc13c3`, version 4, Succeeded.
Run: `864974bf-2fab-4861-8847-43abf65bdef7`.
Receipt: `36f0db1a-e81e-4e28-9dae-74894aa1d1e4`.
ArmorIQ Plan: `4cabf02c-e044-4ce3-a2a4-25970d61f94c`.
Remote Allow request: `0fe47fae-581d-45fc-b4b3-5d4621da8e12`.
Policy `c4b4d803-aefd-4c74-bc0c-dbb4564d399c` targets registered MCP
`0b4133a0-9acd-451b-84a2-a795d9c593c5`; fresh before/after inventories match.

[Documented SDK lifecycle](https://docs.armoriq.ai/sdk/sessions) uses `check` for
mode-aware enforcement and `report` after execution; `complete_plan` is a client
method. The installed SDK can return normally despite audit/status failures, so
this adapter records actual HTTP results. Independent
[organization observability reads](https://docs.armoriq.ai/platform/observability/api-reference)
require Bearer JWT. Remaining verification needs the existing organization's
authenticated read access and the matching Plan/audit record; no new business
execution, deployment or policy change is needed. The no-write probe was not
reported as successful business execution. Failure lifecycle support and wider
application integration are outside this narrow qualification adapter.

Private evidence under `.artifacts/phase23-20261012/`: `baseline.json`,
`no-write-result.json`, `business-result.json`, `disk-and-preservation.json`,
`focused-stable.xml`, `full.xml`, `final-preservation.json`, `delivery-checks.json`,
and the qualification/verification scripts.
These retain correlation IDs, hashes and synthetic records, not raw API keys,
JWTs or signed permits. Generated private runtime keys remain in ignored state.
Adapter SHA-256 for both real trials:
`24884352ec1d3ec82ac5961a26d3b79646a95decd2b72a1d32eaffc2c0850702`.

All 4,347 readable existing protected files retain SHA-256; one locked owner file
retains size/time metadata. All 60 pre-existing source files (including the
Phase 2.2 report) and 73 installed Core/SDK Python files are unchanged. Previous
Unknown Actions were not opened for execution, retried, reconciled or modified.
HEAD remains `7a312530f799bf12fc4b365e21f3dd9e40bc145a`.
