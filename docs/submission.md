# Aegis Relay — submission draft

**Trust the intent. Govern the action.**

A permissioned AI agent for secure incident handoffs.

Repository: https://github.com/miku-wwl/aig-flow-state

Project summary: Aegis Relay turns synthetic incident context into a bounded plan
using local Ollama. The operator reviews and approves the exact persisted plan,
then independently authorizes execution. The frozen Agentic Intent Gate runtime
claims one durable Action. A signed dispatch permit binds that Action and payload
to the protected MCP. In real mode, ArmorIQ captures the reviewed step, issues an
intent token and governs proxy forwarding. The MCP writes one handoff; Aegis Relay
accepts success only after checking its receipt against persisted business data.

Boundary demonstration: show the approved handoff succeeding once, then capture
a separate valid intent for `purge_incident_history` and show the assigned ArmorIQ
deny policy rejecting it with zero forbidden effects. The canary is nondestructive
even if allowed accidentally. Show that core approval alone cannot execute, and
that an ambiguous response remains Unknown without automatic redispatch.

Current evidence: local implementation, actual SDK integration tests, local MCP
protocol, Chrome/Ollama, persistence, replay and restart checks are qualified.
Real agent/MCP registration, temporary protected public discovery and genuine canary
policy denial were verified. The real handoff ended Unknown with zero local business
records; successful forwarding/receipt and dashboard audit remain unqualified.
**Do not submit this draft as a fully qualified live project yet.**
Phase 2.1 local corrections pass the full 128-case offline suite, including 11
Chrome tests. Fresh real SDK inventory still contains zero tools and the retired
endpoint. No fresh real write was attempted. See [the current diagnosis](phase2-blocker-diagnosis.md).
Video URL: not recorded. Public demo URL: not deployed. Real audit/registration
links: not captured. Phase 2 commit URL: not committed. Do not invent these links.

## Verified competition information

Checked 11 October 2026 against the official
[Flow State page](https://armoriq.ai/hackathons/flow-state) and its linked
[Luma registration](https://luma.com/tttqkw24). The event runs 10–17 October 2026,
online; submissions close 17 October. The landing page uses UTC and says exact
deadline hours belong in the official rules, but does not provide an exact hour
or an itemized submission form in the retrieved content. Do not assume Auckland
midnight. Luma describes solo participation or teams of up to four and host approval
for registration. No registration request was submitted in this task.

The public page asks for a working project, short demo and explanation of ArmorIQ
use and boundary behavior. Check the current organizer community for the final
rules, precise deadline and submission destination before submitting.

## Human completion checklist

1. Connect an already authenticated existing-organization browser for read-only
   investigation of the retained Unknown Action's platform Plan and proxy audit.
   Choose the researched SDK-only variant review or approve the prepared free
   ngrok assigned-subdomain route; no self-owned domain/DNS change is needed.
2. Confirm the actual policy's active status/deny rule and correct protected MCP
   routing/credential configuration. SDK registration and a genuine deny already ran.
3. Preserve Unknown without automatic reconciliation or retry. Successful real
   execution, one durable matching receipt and dashboard correlation remain required
   through a separately reviewed safe qualification plan after diagnosis.
4. Record a 2–3 minute demo using [the script](demo-script.md), upload it,
   and insert its real URL. Publish only sanitized evidence.
5. Review current competition rules/deadline/submission form and registration status.
6. Explicitly authorize commit/push when the qualified changes are ready, then
   insert the actual commit link. Final submission requires separate authorization.
   Publish only the audited source package; the old workspace ZIP contains keys.

**READY_TO_SUBMIT=NO · ACTUALLY_SUBMITTED=NO**
