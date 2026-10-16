'use strict';

const $ = id => document.getElementById(id);
let capability = '', run = null, action = null, lastExecution = null, busy = false, scope = null;
let sdkOnly = false, sdkStage = null, executionPath = 'unknown', statusData = null;
let businessRecords = [], businessRecordsLoaded = false, policyEvidence = null;
let publicDemo = false, demoCsrf = '';

const buttons = ['generate','approve','reject','admit','authorize','prepare-sdk','execute','try-unauthorized','replay','restore','refresh-records','policy-test'];
const stageLabels = {complete:'Complete',current:'Current',pending:'Pending',failed:'Failed',unknown:'Unknown','not-applicable':'N/A'};

function controls() {
  const unlocked = publicDemo ? !!demoCsrf : !!capability;
  buttons.forEach(id => $(id).disabled = busy || !unlocked);
  $('start-demo').disabled = busy;
  ['approve','reject'].forEach(id => $(id).disabled ||= run?.state !== 'AwaitingApproval');
  $('admit').disabled ||= run?.state !== 'Approved' || !!action;
  $('authorize').disabled ||= action?.state !== 'Pending';
  $('execute').disabled ||= action?.state !== 'Authorized';
  $('prepare-sdk').disabled ||= !sdkOnly || action?.state !== 'Authorized' || !['MISSING','EXPIRED'].includes(sdkStage?.status);
  $('execute').disabled ||= sdkOnly && (sdkStage?.status !== 'READY' || Date.now()/1000 >= sdkStage.expires_at);
  $('try-unauthorized').disabled ||= action?.state !== 'Pending';
  $('replay').disabled ||= !lastExecution;
  $('copy-run').disabled = !run;
  $('copy-action').disabled = !action;
  const receiptReference = action?.result?.receipt_reference;
  $('copy-receipt').disabled = !receiptReference;
  $('copy-success-receipt').disabled = !receiptReference || action?.state !== 'Succeeded';
  $('workspace-state').textContent = publicDemo ? unlocked ? 'DEMO SESSION READY' : 'DEMO SESSION PAUSED' : capability ? 'WORKSPACE UNLOCKED' : 'WORKSPACE LOCKED';
  $('workspace-state').dataset.unlocked = String(unlocked);
}

function message(id, text) { $(id).textContent = text; $(id).hidden = !text; }

async function api(path, {body, key, expectedError = false} = {}) {
  const headers = {};
  if (capability && !publicDemo) headers.Authorization = 'Bearer ' + capability;
  if (publicDemo && demoCsrf) headers['X-Aegis-CSRF'] = demoCsrf;
  if (path === '/api/demo/session') headers['X-Aegis-Demo'] = '1';
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (key) headers['Idempotency-Key'] = key;
  const response = await fetch(path, {method:body === undefined ? 'GET':'POST', headers, body:body === undefined ? undefined : JSON.stringify(body), cache:'no-store', credentials:publicDemo || path === '/api/status' ? 'same-origin' : 'omit'});
  const data = await response.json();
  if (!response.ok && !expectedError) throw new Error(`${data.error?.code || 'HTTP_' + response.status}: ${data.error?.message || 'Request denied'}`);
  return {response, data};
}

async function perform(task) {
  if (busy) return;
  busy = true; message('error',''); message('notice',''); controls();
  try { await task(); } catch (error) { message('error',error.message); }
  finally { busy = false; controls(); }
}

function compactId(value, head = 8, tail = 5) {
  if (!value) return '—';
  return value.length > head + tail + 3 ? `${value.slice(0,head)}…${value.slice(-tail)}` : value;
}

function renderRun() {
  $('run-state').textContent = run?.state || 'No Run selected';
  $('run-state').dataset.state = run?.state || 'empty';
  $('run-version').textContent = run ? `Version ${run.version}` : '';
  $('run-id').textContent = run ? `Run ${compactId(run.run_id)}` : 'No Run selected';
  $('run-id').title = run?.run_id || '';
  $('plan-json-details').hidden = !run;
  $('run-identifier-row').hidden = !run;
  $('restore-id').value = run?.run_id || '';
  $('plan-json').textContent = run?.plan ? JSON.stringify(run.plan,null,2) : 'No validated Plan.';
  $('full-identifiers').textContent = [run && `Run ID: ${run.run_id}`, action && `Action ID: ${action.action_id}`, action?.result?.receipt_reference && `Receipt: ${action.result.receipt_reference}`].filter(Boolean).join('\n');
  $('validation').textContent = run?.plan ? `Validated by the shared Runtime · Risk: ${run.risk_class}` : run?.error ? `${run.error.code}: ${run.error.message}` : 'Generate a Plan to see validation and risk.';
  $('plan-fields').replaceChildren();
  const step = run?.plan?.steps?.[0];
  if (run?.plan && step) {
    const args = step.arguments || {};
    Object.entries({'Goal':run.plan.goal,'Target':run.plan.target,'Tool':step.tool_name,'Incident':args.incident_id,'Summary':args.summary,'Handoff note':args.handoff_note}).forEach(([name,value]) => {
      if (value === undefined || value === null || value === '') return;
      const dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent=name; dd.textContent=String(value); $('plan-fields').append(dt,dd);
    });
  }
  renderPresentation();
}

function policyOutcome() {
  const policy = sdkStage?.policy;
  if (policy) {
    const decision = policy.action || 'unconfirmed';
    const confirmed = policy.explicit_allow_confirmed === true;
    const prefix = policy.transport === 'OFFLINE_TEST' ? 'Offline SDK fixture' : 'ArmorIQ remote';
    return `${prefix}: ${decision} · Explicit Allow ${confirmed ? 'confirmed' : 'not confirmed'}`;
  }
  if (executionPath === 'mock') return 'Not available · LOCAL / MOCK path';
  if (executionPath === 'proxy') return 'Not separately reported for this Action';
  return 'No policy response recorded';
}

function renderSuccess() {
  const succeeded = action?.state === 'Succeeded';
  $('success-summary').hidden = !succeeded;
  if (!succeeded) return;
  $('success-title').textContent = publicDemo ? 'Simulated handoff: Succeeded' : 'Core Action: Succeeded';
  const step = run?.plan?.steps?.[0];
  const args = step?.arguments || {};
  const receipt = action?.result?.receipt_reference || '';
  const match = businessRecords.find(record => record.receipt_reference === receipt);
  $('success-incident').textContent = args.incident_id || 'Not available in loaded Plan';
  $('success-tool').textContent = step?.tool_name || 'Not available in loaded Plan';
  $('success-record').textContent = match ? `Matched persisted handoff · ${match.incident_id}` : businessRecordsLoaded ? 'No matching business record found' : 'Business record not loaded';
  $('success-policy').textContent = policyOutcome();
  $('success-receipt').textContent = receipt || 'Not available in Action result';
  $('success-receipt').title = receipt;
}

function setStep(key, state) {
  const item = document.querySelector(`[data-step="${key}"]`);
  if (!item) return;
  item.dataset.state = state;
  if (state === 'current') item.setAttribute('aria-current','step');
  else item.removeAttribute('aria-current');
  item.querySelector('.step-state').textContent = stageLabels[state] || 'Not available';
}

function workflowStates() {
  const terminalAfterAuthorization = ['Authorized','Executing','Succeeded','Failed','Unknown'];
  let preparation = 'not-applicable';
  if (sdkOnly) {
    if (['READY','CONSUMED'].includes(sdkStage?.status)) preparation = 'complete';
    // A terminal stage retains its prepared Plan ID after execution and restoration.
    else if (sdkStage?.status === 'TERMINAL_OR_EXECUTING' && sdkStage.plan_id) preparation = 'complete';
    else if (['INVALID','EXPIRED','PREPARATION_FAILED'].includes(sdkStage?.status)) preparation = 'failed';
    else if (action?.state === 'Authorized') preparation = 'current';
    else preparation = 'pending';
  }
  return {
    incident: run ? 'complete' : 'current',
    plan: run?.plan ? 'complete' : run?.error ? 'failed' : 'pending',
    approval: run?.state === 'Approved' ? 'complete' : run?.state === 'Rejected' ? 'failed' : run?.state === 'AwaitingApproval' ? 'current' : 'pending',
    admission: action ? 'complete' : run?.state === 'Approved' ? 'current' : 'pending',
    authorization: action?.state === 'Pending' ? 'current' : terminalAfterAuthorization.includes(action?.state) ? 'complete' : 'pending',
    preparation,
    execution: action?.state === 'Succeeded' ? 'complete' : action?.state === 'Failed' ? 'failed' : action?.state === 'Unknown' ? 'unknown' : action?.state === 'Executing' || action?.state === 'Authorized' && (!sdkOnly || sdkStage?.status === 'READY') ? 'current' : 'pending',
    receipt: action?.result?.receipt_reference ? 'complete' : action?.state === 'Unknown' ? 'unknown' : action?.state === 'Failed' ? 'failed' : 'pending',
  };
}

function evidenceState(status) { return stageLabels[status] ? status : 'unknown'; }

function timelineEntry(index, title, state, detail) {
  const item = document.createElement('li'); item.className = 'evidence-entry'; item.dataset.state = state;
  const number = document.createElement('span'); number.className = 'evidence-index'; number.textContent = String(index).padStart(2,'0');
  const copy = document.createElement('div'); copy.className = 'evidence-copy';
  const heading = document.createElement('strong'); heading.textContent = title;
  const description = document.createElement('p'); description.textContent = detail;
  const badge = document.createElement('span'); badge.className = 'evidence-status'; badge.textContent = stageLabels[state] || 'Not available';
  copy.append(heading,description); item.append(number,copy,badge); return item;
}

function renderTimeline() {
  const items = [];
  const planState = run?.plan ? 'complete' : run?.error ? 'failed' : 'pending';
  items.push(['Plan validated',planState,run?.plan ? `Shared Runtime validation · Risk ${run.risk_class}` : run?.error ? `${run.error.code}: ${run.error.message}` : 'No validated Plan loaded.']);

  const approvalState = run?.state === 'Approved' ? 'complete' : run?.state === 'Rejected' || run?.state === 'PlanRejected' ? 'failed' : run?.state === 'AwaitingApproval' ? 'current' : 'pending';
  const approvalText = run?.state === 'Approved' ? `Human decision recorded · current approved Run version ${run.version}.` : run?.state === 'Rejected' ? 'Plan rejected; no Action was admitted.' : run?.state === 'AwaitingApproval' ? 'Awaiting an explicit decision on this exact Plan.' : 'No approval decision recorded.';
  items.push(['Human approval',approvalState,approvalText]);

  items.push(['Action admission',action ? 'complete' : run?.state === 'Approved' ? 'current' : 'pending',action ? `Durable Action ${compactId(action.action_id)} · ${action.state}.` : run?.state === 'Approved' ? 'Approved Plan can be admitted as a separate step.' : 'No Action admitted.']);
  const authorized = ['Authorized','Executing','Succeeded','Failed','Unknown'].includes(action?.state);
  items.push(['Independent authorization',action?.state === 'Pending' ? 'current' : authorized ? 'complete' : 'pending',action?.state === 'Pending' ? 'Action is Pending; independent authorization is required.' : authorized ? `Action state confirms authorization preceded execution · ${action.state}.` : 'No authorization recorded.']);

  let prepState = 'not-applicable', prepText = `Not required for the ${executionPath === 'unknown' ? 'current' : executionPath.toUpperCase()} execution path.`;
  if (sdkOnly) {
    prepState = sdkStage?.status === 'READY' || sdkStage?.status === 'CONSUMED' || sdkStage?.status === 'TERMINAL_OR_EXECUTING' && sdkStage.plan_id ? 'complete' : ['INVALID','EXPIRED','PREPARATION_FAILED'].includes(sdkStage?.status) ? 'failed' : action?.state === 'Authorized' ? 'current' : 'pending';
    prepText = sdkStage ? `Server-reported SDK stage: ${sdkStage.status}${sdkStage.expires_at ? ` · Expires ${new Date(sdkStage.expires_at*1000).toISOString()}` : ''}.` : action ? 'SDK stage has not been read or prepared.' : 'Requires an exact Authorized Action.';
  }
  items.push(['SDK preparation',prepState,prepText]);

  const policy = sdkStage?.policy;
  let policyState = executionPath === 'mock' ? 'not-applicable' : 'pending';
  let policyText = executionPath === 'mock' ? 'No remote policy request is made in LOCAL / MOCK mode.' : 'No Action-specific remote policy response is available yet.';
  if (policy) {
    policyState = policy.explicit_allow_confirmed === true ? 'complete' : /block|deny/i.test(policy.action || '') ? 'failed' : 'unknown';
    policyText = `${policy.transport === 'OFFLINE_TEST' ? 'Offline SDK fixture' : 'ArmorIQ remote'} · ${policy.action || 'decision unconfirmed'} · Explicit Allow ${policy.explicit_allow_confirmed === true ? 'confirmed' : 'not confirmed'} · Request ${compactId(policy.server_request_id || '')}.`;
  } else if (executionPath === 'proxy') {
    policyState = 'unknown'; policyText = 'The current API does not expose a correlated policy decision for this Action.';
  }
  items.push(['ArmorIQ remote policy decision',policyState,policyText]);

  let permitState = executionPath === 'mock' ? 'not-applicable' : 'unknown';
  let permitText = executionPath === 'mock' ? 'No SDK permit is used in the mock path.' : 'A separate consumer permit-validation event is not exposed by the status API.';
  if (sdkOnly && sdkStage?.audit?.diagnostics?.execution?.late_permit_verified === true) {
    permitState = 'complete'; permitText = 'Consumer execution diagnostics confirm the late signed dispatch permit was verified.';
  } else if (sdkOnly && sdkStage?.status === 'READY') {
    permitState = 'pending'; permitText = 'The exact Authorized SDK stage is READY. Execution-time permit verification has not yet been reported.';
  } else if (sdkOnly && sdkStage?.status === 'CONSUMED') {
    permitState = 'unknown'; permitText = 'The prepared stage is consumed; no separate permit-validation trace is returned.';
  }
  items.push(['Consumer permit / argument validation',permitState,permitText]);

  const executionState = action?.state === 'Succeeded' ? 'complete' : action?.state === 'Failed' ? 'failed' : action?.state === 'Unknown' ? 'unknown' : action?.state === 'Executing' || action?.state === 'Authorized' && (!sdkOnly || sdkStage?.status === 'READY') ? 'current' : 'pending';
  const executionText = action?.state === 'Authorized' ? 'Authorization is recorded; waiting for an explicit Execute Once action.' : action ? `Core Action state: ${action.state}. ${action.state === 'Unknown' ? 'Outcome remains ambiguous; no automatic retry.' : ''}` : 'Execution has not been requested.';
  items.push(['Action execution result',executionState,executionText]);
  const receipt = action?.result?.receipt_reference;
  const receiptState = receipt ? 'complete' : action?.state === 'Unknown' ? 'unknown' : action?.state === 'Failed' ? 'failed' : 'pending';
  items.push(['Durable receipt',receiptState,receipt ? `Receipt reference ${compactId(receipt)}.` : action?.state === 'Unknown' ? 'No receipt is confirmed for this Unknown outcome.' : 'No durable receipt is available yet.']);

  const audit = sdkStage?.audit;
  let auditState = executionPath === 'sdk-only' ? 'pending' : 'not-applicable';
  let auditText = executionPath === 'sdk-only' ? 'No audit report is recorded for this Action yet.' : 'Audit reporting detail is not available in this execution path.';
  if (sdkStage?.audit_storage === 'UNAVAILABLE') { auditState = 'unknown'; auditText = 'Audit storage is unavailable; Core state and receipt remain separate.'; }
  else if (audit) {
    const auditStatus = audit.status || audit.event_type || 'Recorded';
    auditState = auditStatus === 'SDK_AUDIT_POST_ACKNOWLEDGED' ? 'complete' : /UNVERIFIED|FAILED/i.test(auditStatus) ? 'unknown' : 'complete';
    auditText = `Backend audit status: ${auditStatus}.`;
  } else if (sdkOnly && action && ['Succeeded','Failed','Unknown'].includes(action.state)) {
    auditState = 'unknown'; auditText = 'Terminal Action is visible; no audit event is returned for this Action.';
  }
  items.push(['Audit reporting status',auditState,auditText]);

  const list = $('timeline'); list.replaceChildren();
  items.forEach((entry,index) => list.append(timelineEntry(index+1,...entry)));
}

function renderPresentation() {
  const states = workflowStates();
  for (const [key,state] of Object.entries(states)) setStep(key,state);
  renderTimeline();
  renderSuccess();
}

function renderAction() {
  $('action-state').textContent = action?.state || 'No Action admitted';
  $('action-state').dataset.state = action?.state || 'empty';
  $('action-id').textContent = action ? `Action ${compactId(action.action_id)} · v${action.version}` : '—';
  $('action-id').title = action?.action_id || '';
  $('receipt').textContent = compactId(action?.result?.receipt_reference || '');
  $('receipt').title = action?.result?.receipt_reference || '';
  $('action-json').textContent = action ? JSON.stringify(action,null,2) : 'No Action yet.';
  $('full-identifiers').textContent = [run && `Run ID: ${run.run_id}`, action && `Action ID: ${action.action_id}`, action?.result?.receipt_reference && `Receipt: ${action.result.receipt_reference}`].filter(Boolean).join('\n');
  const explanations = {Pending:'Approval is recorded. Independent authorization is still required.',Authorized:sdkOnly ? 'Authorization is recorded. Prepare the SDK stage explicitly, then execute once.' : 'Authorization is recorded. Execute only as an explicit operator action.',Succeeded:'Backend confirms success. Match the durable receipt with the business record below.',Failed:'Backend reports a confirmed failure. Inspect available policy evidence.',Unknown:'Outcome unknown: a handoff may exist. No automatic retry or redispatch is permitted.',Executing:'Backend execution is in progress; refresh only reads state.'};
  $('action-message').textContent = explanations[action?.state] || 'Awaiting your review.';
  renderPresentation();
  controls();
}

async function readStage() {
  sdkStage = null;
  const statusNodes = ['sdk-stage-status','sdk-policy-status','sdk-audit-status'];
  statusNodes.forEach(id => $(id).hidden = !sdkOnly);
  $('sdk-control-description').textContent = sdkOnly ? 'Explicit, ephemeral preparation. No business write.' : 'Not used by the current execution path.';
  if (!sdkOnly || !action) {
    $('sdk-stage-status').textContent = sdkOnly ? 'SDK stage: requires an exact Approved and Authorized Action.' : '';
    $('sdk-policy-status').textContent = sdkOnly ? 'ArmorIQ policy: no execution decision requested.' : '';
    $('sdk-audit-status').textContent = sdkOnly ? 'Audit: no Action selected.' : '';
    renderPresentation();
    return;
  }
  const {data} = await api(`/api/actions/${action.action_id}/sdk-stage`);
  sdkStage = data;
  const policy = data.policy;
  $('sdk-policy-status').textContent = policy ? `${policy.transport === 'OFFLINE_TEST' ? 'OFFLINE SDK fixture' : 'ArmorIQ remote'} policy response: ${policy.action || 'unconfirmed'} · Tool ${policy.tool} · Explicit Allow ${policy.explicit_allow_confirmed ? 'CONFIRMED' : 'NOT CONFIRMED'} · Policy ${policy.policy_name || 'unmatched'} (${policy.policy_id || 'unmatched'}) · Request ${policy.server_request_id || 'unavailable'}. Argument and permit details remain server-side.` : 'Policy: no execution decision recorded.';
  $('sdk-stage-status').textContent = `SDK stage: ${data.status}${data.plan_id ? ' · Plan ' + compactId(data.plan_id) : ''}${data.expires_at ? ' · Expires ' + new Date(data.expires_at*1000).toISOString() : ''}. Tokens remain on the server.`;
  const audit = data.audit;
  $('sdk-audit-status').textContent = data.audit_storage === 'UNAVAILABLE' ? 'Audit storage unavailable. Core result and receipt remain durable; no automatic reporting or business retry.' : audit ? `Audit: ${audit.status || audit.event_type || 'recorded'} · Remote audit ${audit.diagnostics?.http_events?.find(e=>e.phase==='REPORT')?.audit_id || 'unverified'}. POST acknowledgement is separate from dashboard persistence.` : 'Audit: not reported. Business success is verified by Core and the durable receipt.';
  renderPresentation();
}

async function records() {
  const {data} = await api('/api/handoffs');
  businessRecords = data.records; businessRecordsLoaded = true;
  $('records').replaceChildren();
  if (!data.records.length) { const p=document.createElement('p'); p.className='empty'; p.textContent='No handoff records yet.'; $('records').append(p); }
  data.records.forEach(record => {
    const item=document.createElement('article'); item.className='record'; item.dataset.receipt=record.receipt_reference;
    [['strong',record.incident_id + ' · ' + record.summary],['p',record.handoff_note],['p','Receipt ' + record.receipt_reference],['p','Effect ' + record.effect_key + ' · ' + record.created_at]].forEach(([tag,text],index) => {const child=document.createElement(tag); child.textContent=text; if(index>=2)child.className='identifier'; item.append(child);}); $('records').append(item);
  });
  const evidence = await api('/api/policy/evidence');
  policyEvidence = evidence.data;
  const currentEvent = action ? evidence.data.events.filter(event => event.action_id === action.action_id).at(-1) : null;
  $('live-evidence').textContent = evidence.data.mode === 'LIVE' && currentEvent ? `${currentEvent.status || currentEvent.event_type || 'Audit event recorded'} · Action ${compactId(currentEvent.action_id || '')} · Plan ${compactId(currentEvent.plan_id || '')} · Receipt ${compactId(currentEvent.receipt_reference || '')}` : '';
  renderPresentation();
}

async function loadRun(id) {
  const {data} = await api('/api/runs/' + encodeURIComponent(id)); run=data;
  $('intent').value = run.intent.text;
  localStorage.setItem('safeops-run-' + scope,run.run_id); renderRun();
  const actions = await api(`/api/runs/${run.run_id}/actions`); action=actions.data.actions[0] || null; lastExecution=null; renderAction(); await readStage();
}

async function updateStatus() {
  const {data} = await api('/api/status'); statusData=data; scope=data.execution_scope;
  publicDemo = data.public_demo === true;
  demoCsrf = publicDemo ? data.demo_csrf || '' : '';
  $('public-banner').hidden = !publicDemo;
  $('public-history').hidden = !publicDemo;
  $('start-demo').hidden = !publicDemo;
  $('capability-file').parentElement.hidden = publicDemo;
  $('capability-file').disabled = publicDemo;
  if (publicDemo) {
    $('access-title').textContent = 'Isolated public demo session';
    $('capability-status').textContent = 'Your session uses synthetic data and simulated effects. Private operator credentials are not accepted.';
    $('lock').textContent = 'Pause demo controls';
    $('intent').maxLength = 1500;
    $('public-history-links').replaceChildren();
    for (const item of data.historical_evidence || []) {
      const p=document.createElement('p'), a=document.createElement('a');
      a.textContent=item.label; a.href=item.source; a.target='_blank'; a.rel='noopener noreferrer';
      p.append(a,document.createElement('br'),document.createTextNode(item.detail));
      $('public-history-links').append(p);
    }
  }
  executionPath=data.execution_path || 'unknown';
  $('provider-mode').textContent = data.provider.mode === 'fixture' ? 'Deterministic fixture · offline' : data.provider.mode === 'deepseek' ? `DeepSeek · ${data.provider.model} · thinking disabled` : `Live local Ollama · ${data.provider.model || 'discover phi4-mini'}`;
  const live = data.enforcement === 'LIVE';
  sdkOnly = data.execution_path === 'sdk-only';
  const offline = live && data.armoriq?.transport === 'OFFLINE_TEST';
  $('prepare-sdk').hidden = !sdkOnly;
  $('mode-chip').textContent = publicDemo ? 'PUBLIC SIMULATION' : offline ? 'LOCAL / OFFLINE SDK TEST' : sdkOnly ? 'ARMORIQ SDK-ONLY LIVE' : live ? 'PROXY LIVE' : 'LOCAL / MOCK';
  $('mode-chip').dataset.mode = offline ? 'offline' : live ? 'live' : 'mock';
  $('enforcement-mode').textContent = data.enforcement_label;
  $('integration-status').textContent = live ? offline ? 'OFFLINE TEST TRANSPORT · no platform request' : `Connectivity ${data.armoriq.connectivity} · Registration ${data.armoriq.registration}` : 'Not connected · local mock only';
  $('policy-lab-label').textContent = offline ? 'OFFLINE POLICY FIXTURE' : sdkOnly ? 'HISTORICAL PLATFORM REFERENCE' : live ? 'LIVE POLICY BOUNDARY' : 'LOCAL MOCK POLICY LAB';
  $('policy-origin-label').textContent = offline ? 'OFFLINE TEST MODE · NO LIVE PLATFORM REQUEST' : sdkOnly ? 'HISTORICAL ARMORIQ REFERENCE AVAILABLE ON REQUEST' : live ? 'POLICY PROBE REQUIRES AN EXPLICIT OPERATOR CLICK' : 'LOCAL MOCK EVIDENCE · NOT ARMORIQ';
  $('sdk-control-description').textContent = sdkOnly ? 'Explicit, ephemeral preparation. No business write.' : 'Not used by the current execution path.';
  $('policy-lab-description').textContent = sdkOnly ? 'Load the preserved Phase 2.2 denial reference. The backend returns its historical ID without a new remote request.' : offline ? 'Uses a deterministic offline transport. It cannot qualify live platform enforcement.' : live ? 'The explicit probe uses the configured live boundary; it is never called on page load.' : 'Runs a deterministic local policy check. No ArmorIQ call and no Core Action.';
  $('policy-test').textContent = sdkOnly ? 'Load historical denial reference' : offline ? 'Run offline policy fixture' : live ? 'Run explicit policy denial probe' : 'Test local mock denial';
  $('mode-footer').textContent = `Agentic Intent Gate v0.1.0 · One trusted SIDE_EFFECT tool · ${offline ? 'Offline SDK transport — no live qualification' : live ? 'Live ArmorIQ path — backend status and evidence only' : 'Local mock execution path'}`;
  renderPresentation();
  controls();
  return data;
}

$('start-demo').onclick = () => perform(async () => {
  const {data}=await api('/api/demo/session',{body:{}}); demoCsrf=data.demo_csrf;
  await updateStatus(); await records();
  const remembered=localStorage.getItem('safeops-run-' + scope);
  if (remembered) await loadRun(remembered);
});

async function copyValue(value, label) {
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    message('notice',`${label} copied.`);
  } catch {
    message('error',`Clipboard access is unavailable. The full ${label.toLowerCase()} remains in the technical details.`);
  }
}

$('copy-run').onclick = () => copyValue(run?.run_id,'Full Run ID');
$('copy-action').onclick = () => copyValue(action?.action_id,'Full Action ID');
$('copy-receipt').onclick = $('copy-success-receipt').onclick = () => copyValue(action?.result?.receipt_reference,'Full receipt reference');

$('capability-file').addEventListener('change', () => perform(async () => {
  const input=$('capability-file'), file=input.files[0]; if(!file)return;
  try { if(file.size>128)throw new Error('Choose the private capability file created by safeops init.'); const text=(await file.text()).trim(); if(!/^[0-9a-f]{64}$/.test(text))throw new Error('Invalid capability file.'); capability=text; }
  finally { input.value=''; }
  try { await updateStatus(); await records(); const remembered=localStorage.getItem('safeops-run-' + scope); if(remembered)await loadRun(remembered); }
  catch(error) { capability=''; controls(); throw error; }
  $('capability-status').textContent='Workspace unlocked. Capability remains only in browser memory; reload it after refresh.';
  controls();
}));

$('lock').onclick = () => {
  demoCsrf='';
  capability=''; run=null; action=null; lastExecution=null; sdkStage=null; businessRecords=[]; businessRecordsLoaded=false; policyEvidence=null;
  renderRun(); renderAction(); $('records').replaceChildren(); $('policy-result').textContent='No policy evidence loaded.'; $('live-evidence').textContent='';
  $('capability-status').textContent='Workspace locked. Load your private capability file.'; controls();
};

$('generate').onclick = () => perform(async () => {
  const {data} = await api('/api/runs',{body:{text:$('intent').value}}); run=data; action=null; lastExecution=null; sdkStage=null;
  localStorage.setItem('safeops-run-' + scope,run.run_id); renderRun(); renderAction(); await readStage();
  const status=await updateStatus();
  if(run.error) { throw new Error(`${run.error.code}: ${run.error.message}${status.provider.last_error ? ' · ' + status.provider.last_error : ''}`); }
  message('notice','Plan validated and Run persisted. Review the exact Plan before approving.');
});

for (const [id,decision] of [['approve','APPROVE'],['reject','REJECT']]) $(id).onclick = () => perform(async () => {
  const {data}=await api(`/api/runs/${run.run_id}/approval`,{body:{decision,expected_version:run.version}}); run=data; renderRun(); message('notice',decision==='APPROVE' ? 'Exact Plan approved. Admit the Action, then authorize it separately.' : 'Plan rejected. No Action executed.');
});

$('admit').onclick = () => perform(async () => {const {data}=await api(`/api/runs/${run.run_id}/actions`,{body:{expected_run_version:run.version},key:crypto.randomUUID()}); action=data.actions[0]; renderAction(); await readStage();});
$('authorize').onclick = () => perform(async () => {const {data}=await api(`/api/actions/${action.action_id}/authorize`,{body:{expected_action_version:action.version},key:crypto.randomUUID()}); action=data.action; renderAction(); await readStage();});
$('prepare-sdk').onclick = () => perform(async () => {
  await api(`/api/actions/${action.action_id}/sdk-stage`,{body:{expected_action_version:action.version}});
  await readStage(); await updateStatus(); await records(); message('notice','Exact Authorized Action prepared. Execute before expiry; preparation creates no business record.');
});
$('execute').onclick = () => perform(async () => {
  lastExecution={path:`/api/actions/${action.action_id}/execute`,body:{expected_action_version:action.version},key:crypto.randomUUID()};
  try { const {data}=await api(lastExecution.path,lastExecution); action=data.action; renderAction(); await records(); }
  finally { await readStage(); }
});
$('replay').onclick = () => perform(async () => {const {data}=await api(lastExecution.path,lastExecution); action=data.action; renderAction(); await records(); message('notice',data.replayed ? 'Exact request replayed. The durable receipt is unchanged.' : 'Backend execution result received.');});
$('try-unauthorized').onclick = () => perform(async () => {
  const {response,data}=await api(`/api/actions/${action.action_id}/execute`,{body:{expected_action_version:action.version},key:crypto.randomUUID(),expectedError:true});
  if(response.ok)throw new Error('Unexpected allowed execution'); message('error',`${data.error.code}: ${data.error.message} · No business effect.`); await records();
});
$('policy-test').onclick = () => perform(async () => {
  const {data}=await api('/api/policy/test',{body:{operation:'purge_incident_history'},expectedError:true});
  if (data.source && data.source.startsWith('Historical')) {
    $('policy-result').textContent = [
      `Source: ${data.source}`,
      `Historical request ID: ${data.historical_request_id || 'not available'}`,
      `Current request status: ${data.status || 'not available'}`,
      `Core Action created: ${data.core_action_created === true ? 'Yes' : 'No'}`,
      `Business effect executed: ${data.business_effect_executed === true ? 'Yes' : 'No'}`,
    ].join('\n');
    $('policy-origin-label').textContent='HISTORICAL ARMORIQ POLICY DENIAL · NOT THIS RUN';
  } else {
    $('policy-result').textContent=JSON.stringify(data,null,2);
    if (data.mode === 'MOCK') $('policy-origin-label').textContent='LOCAL MOCK POLICY DENIAL · NOT ARMORIQ';
    else if (data.policy_denial_verified) $('policy-origin-label').textContent='ARMORIQ POLICY DENIAL · BACKEND VERIFIED';
  }
  await records();
});
$('restore').onclick = () => perform(() => loadRun($('restore-id').value.trim()));
$('refresh-records').onclick = () => perform(async () => {await records(); await readStage();});

setInterval(() => {
  if (sdkStage?.status === 'READY' && Date.now()/1000 >= sdkStage.expires_at) {
    sdkStage.status = 'EXPIRED'; $('sdk-stage-status').textContent = 'SDK stage: EXPIRED. Prepare explicitly before execution.'; renderPresentation(); controls();
  }
}, 500);

renderRun(); renderAction(); controls();
updateStatus().then(async () => {
  if (publicDemo && demoCsrf) {
    await records();
    const remembered=localStorage.getItem('safeops-run-' + scope);
    if (remembered) await loadRun(remembered);
  }
}).catch(error => message('error',error.message));
