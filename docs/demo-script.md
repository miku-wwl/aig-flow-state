# Aegis Relay — 2–3 minute demo script

Use the completed, expressly approved **INC-24001** evidence. A new recording may
restore the existing Succeeded Run read-only. Do not generate another business write,
prepare a terminal Action or replay the historical INC-23001/Unknown. The screenshots
document actual live clicks; a narrated reconstruction must disclose that it uses
captured evidence rather than a newly executed workflow.

Keep credentials, capabilities, tokens, signing keys and private account details
off-screen. The UI file picker clears its input. No HAR or authorization trace.
Record MOCK/offline scenarios with their explicit mode label throughout.

| Time | Screen/action | Narration and evidence |
| --- | --- | --- |
| 0:00–0:20 | Product title, tagline, SDK-only LIVE badge | Aegis Relay governs one incident handoff using the frozen shared runtime and real ArmorIQ SDK policy enforcement. |
| 0:20–0:45 | Actual pre-approval Plan capture | Local phi4-mini proposed the synthetic Plan. Show exact INC-24001 arguments, trusted tool/target and SIDE_EFFECT risk. |
| 0:45–1:05 | Actual approval/admission/authorization evidence | Approval binds this Plan. An unauthorized attempt was denied with zero effects. Independent authorization is a separate gate. |
| 1:05–1:25 | Actual READY stage capture with zero records | Explicit preparation obtains the Plan/token outside the Core execution window. Tokens stay in memory and expiry is enforced. |
| 1:25–1:50 | Actual Succeeded/receipt/one-record capture | Real remote tool-policy Allow preceded local context and late permit checks. Only the SDK-only executor wrote. Core finished in 1.26 seconds within five seconds. |
| 1:50–2:10 | Persisted Run restored read-only | Show the same receipt and one SQLite record after refresh/process restart. Execute and Prepare are disabled for this terminal Action. |
| 2:10–2:30 | Historical denial and platform captures, clearly labelled | Phase 2.2 canary was genuinely blocked. Phase 2.3 platform API detail matched its Action/receipt. These are historical, not new Phase 2.4 rows. |
| 2:30–2:45 | New audit acknowledgement and limitation | Report/completion returned HTTP 200 and the new audit ID. Independent new dashboard readback is still blocked; do not claim observed persistence. |
| 2:45–3:00 | Report, test counts and remaining work | 179 tests, 14 real Chrome tests; frozen Core and old Unknown preserved. Video/submission and authenticated new audit review remain human work. |

New Run: `eb30069a-3aba-4a53-b1c9-d9cd16be2388`.
New Action: `4a6e877c-d60a-4651-b0eb-76058a6bf30e`.
Receipt: `6b42e4b8-4e10-43d8-a832-a5d98d68d1b0`.
Audit ID: `654b662f-11af-4fae-b412-aa3bf4225af9`.
Screenshots and exact paths: [report section G](phase24-application-e2e-report.md#g-screenshots-and-private-evidence).

For a read-only local recording, stop any owner of this exact new state first, then
run the existing application on loopback. Do not use old historical state:

```powershell
uv run safeops serve --state .artifacts/phase24-20261012/fresh-live-browser-state-2 --port 8767 --provider ollama --enforcement-mode sdk-only --predecessor-stopped
```

Open `http://127.0.0.1:8767`, load this state's private capability file, enter the
new Run ID above and click **Open saved Run**. Inspect only; no preparation,
execution, policy test or generation is required. Stop the owned foreground server
after recording. Existing keys stay private; video editing must redact account details
in historical dashboard screenshots without changing the originals.

Optional offline fault evidence may illustrate Unknown without retry, explicitly
labelled OFFLINE. Do not imply exactly-once remote effects or production multi-user
security. No video has been recorded/uploaded, no project submitted and no Phase 2.4
commit published by this task. New business execution needs separate exact approval.
