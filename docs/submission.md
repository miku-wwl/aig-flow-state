# Aegis Relay — submission draft

**Trust the intent. Govern the action.**

A permissioned AI agent for secure incident handoffs.

Repository: https://github.com/miku-wwl/aig-flow-state

This is a copy-ready draft, not a submitted entry. Phase 2.4 changes remain local;
the repository URL does not imply those changes have been published.

## Project description

Aegis Relay turns synthetic incident context into a bounded Plan using local
Ollama. The operator reviews and approves the exact persisted Plan, admits its
Action and independently authorizes execution. The frozen [Agentic Intent Gate](https://github.com/miku-wwl/agentic-intent-gate)
0.1.0 runtime owns these gates, durable claims, identity and outcome handling.

After authorization, the existing FastAPI UI explicitly pre-stages an ArmorIQ
SDK-only Plan/token. During Core's unchanged five-second execution window, actual
ArmorIQ remote enforcement must explicitly Allow the registered handoff tool under
the expected policy. The consumer then revalidates exact arguments and Core context,
issues and verifies a late signed dispatch permit, and commits one SQLite handoff.
Its durable receipt must match before Core succeeds. SDK reporting and Plan completion
follow Core success. This integration uses armoriq-sdk 0.6.10 and needs no public
MCP server, tunnel or custom domain. MOCK and the existing proxy path are preserved.

ArmorIQ Allow is a tool-level policy decision. Exact payload/permit integrity is
verified locally; the project does not claim the remote service verified those fields.
Unknown outcomes never automatically retry. Audit failure cannot repeat the write.

## Actual qualification evidence

One expressly approved fresh synthetic **INC-24001** workflow ran through real
Chrome clicks and real Ollama, then actual HTTPS ArmorIQ Allow. Action
`4a6e877c-d60a-4651-b0eb-76058a6bf30e` reached Succeeded with exactly one durable
record and matching receipt `6b42e4b8-4e10-43d8-a832-a5d98d68d1b0`.
Core claim-to-terminal measured **1,259.307 ms**; remote enforcement **928.855 ms**.
Exact request replay, refresh and real process restart preserved the same record
and receipt. The complete consumer regression is **179 passed**, including
**14 real Chrome tests**, in 369.90 seconds.

SDK audit POST and complete_plan returned HTTP 200, with matching Plan attribution.
New audit ID: `654b662f-11af-4fae-b412-aa3bf4225af9`. Independent new platform
readback is **BLOCKED**: SDK credentials receive 401 on the organization trace API
and there is no connected authenticated dashboard browser. This limitation is explicit.

Historical real canary denial is reused from Phase 2.2; no new canary ran. Six
original ArmorIQ screenshots match their manifest and prove historical visible rows
and the Phase 2.3 API request/Action/receipt correlation. They are not the new
Phase 2.4 platform audit. The earlier proxy Unknown and INC-23001 state remain untouched.
See the [complete A–J report](phase24-application-e2e-report.md) for IDs, timings,
screenshots, security coverage, preservation and limitations.
Setup and mode selection: [README](../README.md#start-locally).

## Competition information

Rechecked 12 October 2026: the [official Flow State page](https://armoriq.ai/hackathons/flow-state)
accepts SDK integration without an MCP server, describes a working project, short
demo and ArmorIQ boundary evidence, and lists submission closing **17 October 2026,
UTC**. It says exact hours publish with official rules; a precise hour and formal
submission destination were not verified. Do not assume Auckland midnight.
[Luma](https://luma.com/tttqkw24) is event registration with host approval, not
project submission evidence. Registration status and final rules still need human review.

## Remaining human work

1. In the existing authenticated organization, locate the new audit ID and verify
   its new Action/receipt attribution. Capture read-only evidence; do not repeat the write.
2. Record and upload a short demo using the [script](demo-script.md). Historical
   screenshots and new application execution must be labelled separately.
3. Confirm registration, official rules, exact UTC deadline and submission form.
4. Separately authorize commit/push or source publication, then insert the actual
   published revision and video URLs. Publish only audited source, never private state.
5. Review the completed entry and separately authorize final submission.

Video URL: NOT RECORDED. Public demo: NOT DEPLOYED (not needed for this spike).
Phase 2.4 commit URL: NOT COMMITTED. Submission receipt: NONE. No links are invented.

**PHASE24_APPLICATION_E2E=PASS · READY_TO_SUBMIT=NO · ACTUALLY_SUBMITTED=NO**
