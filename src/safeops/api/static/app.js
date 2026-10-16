'use strict';

const $ = id => document.getElementById(id);
let capability = '', run = null, action = null, busy = false, scope = null;
let sdkOnly = false, sdkStage = null, executionPath = 'unknown';
let businessRecords = [], businessRecordsLoaded = false;
let publicDemo = false, demoCsrf = '';

const buttons = ['generate','approve','reject','admit','authorize','prepare-sdk','execute'];
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
  $('workspace-state').textContent = publicDemo ? unlocked ? 'SANDBOX READY' : 'SANDBOX PAUSED' : capability ? 'WORKSPACE UNLOCKED' : 'WORKSPACE LOCKED';
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
  $('run-id').textContent = run ? `Run ID: ${run.run_id}` : 'No Run selected';
  $('run-id').title = run?.run_id || '';
  $('plan-json-details').hidden = !run;
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
  $('success-policy-row').hidden = publicDemo;
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

function renderCloudEvidence(bundle) {
  const evidence = bundle?.evidence;
  const timestamp = evidence?.execution_at_utc ? Date.parse(evidence.execution_at_utc) : NaN;
  const verified = bundle?.status === 'VERIFIED'
    && bundle?.current_execution_mode === 'MOCK'
    && evidence?.status === 'VERIFIED'
    && evidence?.transport === 'REAL_PLATFORM'
    && evidence?.decision === 'Allow'
    && evidence?.enforcement_http_status === 200
    && evidence?.action_state === 'Succeeded'
    && evidence?.effect_count === 1
    && evidence?.receipt_matched === true
    && evidence?.audit_status === 'ACKNOWLEDGED'
    && evidence?.audit_http_status === 200
    && evidence?.completion_success === true
    && Number.isFinite(timestamp)
    && typeof evidence?.policy_id === 'string'
    && typeof evidence?.receipt_reference === 'string';
  const set = (id, value) => { $(id).textContent = value ?? 'Not available'; };
  const when = verified
    ? new Date(timestamp).toLocaleString('en-NZ', {timeZone:'UTC', dateStyle:'medium', timeStyle:'short'})
    : 'Not verified';
  $('cloud-evidence').dataset.verification = verified ? 'verified' : 'unverified';
  $('cloud-evidence-status').textContent = verified ? 'VERIFIED' : 'UNVERIFIED';
  $('cloud-evidence-status').dataset.state = verified ? 'verified' : 'unknown';
  $('cloud-evidence-title').textContent = verified ? 'Verified Cloud Execution' : 'Cloud evidence is unverified';
  $('cloud-evidence-eyebrow').textContent = verified
    ? 'AZURE · REAL ARMORIQ ENFORCEMENT'
    : 'ARMORIQ CLOUD INTEGRATION STATUS';
  $('cloud-evidence-message').textContent = verified
    ? 'ArmorIQ returned an explicit Allow. The Core Action succeeded, one durable handoff matched its receipt, and the audit was acknowledged on ' + when + ' UTC.'
    : 'Persisted Run, Action, policy, receipt and audit evidence is missing or inconsistent. No Allow is claimed.';
  set('cloud-evidence-decision', verified ? 'Allow · HTTP ' + evidence.enforcement_http_status : 'Not verified');
  set('cloud-evidence-policy', verified ? 'Registered policy matched' : 'Not verified');
  set('cloud-evidence-action', verified ? 'Succeeded · ' + evidence.tool_name + ' v' + evidence.tool_version : 'Not verified');
  set('cloud-evidence-effect', verified ? 'Exactly 1 · synthetic handoff' : 'Not verified');
  set('cloud-evidence-receipt', verified ? 'Matched durable receipt' : 'Not verified');
  set('cloud-evidence-audit', verified ? 'Acknowledged · HTTP ' + evidence.audit_http_status : 'Not verified');
  set('hero-evidence-status', verified ? 'ArmorIQ Cloud · Verified' : 'ArmorIQ Cloud · Unverified');
  set('hero-evidence-summary', verified
    ? 'Real SDK-only Allow confirmed. This is a previously completed Azure execution.'
    : 'Persisted cloud evidence is unavailable or inconsistent. No Allow is claimed.');
  set('hero-evidence-path', verified ? 'SDK-only · REAL_PLATFORM' : 'Not verified');
  set('hero-evidence-result', verified ? 'Core Succeeded' : 'Not verified');
  set('hero-evidence-receipt', verified ? 'Matched' : 'Not verified');
  $('cloud-evidence-details').hidden = !verified;
  $('cloud-evidence-refs').replaceChildren();
  if (verified) {
    const refs = [
      ['Run', evidence.run_id], ['Action', evidence.action_id], ['Intent Plan', evidence.plan_id],
      ['ArmorIQ enforcement request', evidence.enforcement_request_id], ['Registered policy', evidence.policy_name],
      ['Policy ID', evidence.policy_id], ['Business effect count', String(evidence.effect_count)],
      ['Receipt', evidence.receipt_reference], ['Audit', evidence.audit_id],
      ['Execution UTC', evidence.execution_at_utc], ['Source', evidence.source]
    ];
    for (const [label, value] of refs) {
      const dt = document.createElement('dt'), dd = document.createElement('dd');
      dt.textContent = label; dd.textContent = value; $('cloud-evidence-refs').append(dt, dd);
    }
  }
  return verified;
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
  const authorized = ['Authorized','Executing','Succeeded','Failed','Unknown'].includes(action?.state);
  const stageReady = !sdkOnly || ['READY','CONSUMED'].includes(sdkStage?.status)
    || sdkStage?.status === 'TERMINAL_OR_EXECUTING' && !!sdkStage.plan_id;
  const executionState = action?.state === 'Succeeded' ? 'complete'
    : action?.state === 'Failed' ? 'failed'
      : action?.state === 'Unknown' ? 'unknown'
        : action?.state === 'Executing' ? 'current'
          : action?.state === 'Authorized' && stageReady ? 'current' : 'pending';
  const receipt = action?.result?.receipt_reference;
  return {
    plan: run?.plan ? 'complete' : run?.error ? 'failed' : 'pending',
    approval: run?.state === 'Approved' ? 'complete' : ['Rejected','PlanRejected'].includes(run?.state) ? 'failed' : run?.state === 'AwaitingApproval' ? 'current' : 'pending',
    admission: action ? 'complete' : run?.state === 'Approved' ? 'current' : 'pending',
    authorization: action?.state === 'Pending' ? 'current' : authorized ? 'complete' : 'pending',
    execution: executionState,
    receipt: receipt ? 'complete' : action?.state === 'Unknown' ? 'unknown' : action?.state === 'Failed' ? 'failed' : 'pending',
  };
}

function renderPresentation() {
  const states = workflowStates();
  for (const [key,state] of Object.entries(states)) setStep(key,state);
  renderSuccess();
}

function renderAction() {
  $('action-state').textContent = action?.state || 'No Action admitted';
  $('action-state').dataset.state = action?.state || 'empty';
  $('action-json').textContent = action ? JSON.stringify(action,null,2) : 'No Action yet.';
  $('full-identifiers').textContent = [run && `Run ID: ${run.run_id}`, action && `Action ID: ${action.action_id}`, action?.result?.receipt_reference && `Receipt: ${action.result.receipt_reference}`].filter(Boolean).join('\n');
  const explanations = {Pending:'Plan approval is recorded. Independent authorization is still required.',Authorized:sdkOnly ? 'Authorization is recorded. Prepare the SDK stage explicitly, then execute once.' : 'Authorization is recorded. Execute only as an explicit operator action.',Succeeded:'Backend confirmed the Action and durable receipt.',Failed:'Backend reports a confirmed failure. No success is claimed.',Unknown:'Outcome unknown: a handoff may exist. No automatic retry or redispatch is permitted.',Executing:'Backend execution is in progress; refresh only reads state.'};
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
  renderSuccess();
}

async function loadRun(id) {
  const {data} = await api('/api/runs/' + encodeURIComponent(id)); run=data;
  $('intent').value = run.intent.text;
  localStorage.setItem('safeops-run-' + scope,run.run_id); renderRun();
  const actions = await api(`/api/runs/${run.run_id}/actions`); action=actions.data.actions[0] || null; renderAction(); await readStage();
}

async function updateStatus() {
  const {data} = await api('/api/status'); scope=data.execution_scope;
  publicDemo = data.public_demo === true;
  demoCsrf = publicDemo ? data.demo_csrf || '' : '';
  $('playground-disclosure').hidden = !publicDemo;
  $('cloud-evidence').hidden = !publicDemo;
  $('start-demo').hidden = !publicDemo;
  $('capability-file').parentElement.hidden = publicDemo;
  $('capability-file').disabled = publicDemo;
  $('lock').hidden = publicDemo;
  const cloudVerified = renderCloudEvidence(data.armoriq_evidence);
  if (publicDemo) {
    $('access-title').textContent = 'Isolated sandbox session';
    $('capability-status').textContent = 'Start a private demo session to explore the governed workflow.';
    $('start-demo').textContent = 'Start sandbox session';
    $('intent').maxLength = 1500;
  } else {
    $('access-title').textContent = 'Operator capability';
    $('capability-status').textContent = 'Load your private capability file to unlock this workspace. It stays in browser memory.';
    $('lock').textContent = 'Lock workspace';
    $('intent').maxLength = 4096;
  }
  executionPath=data.execution_path || 'unknown';
  const providerLabel = data.provider.mode === 'fixture'
    ? 'Deterministic fixture · offline'
    : data.provider.mode === 'deepseek'
      ? 'DeepSeek · ' + (data.provider.model || 'model')
      : 'Ollama · ' + (data.provider.model || 'local model');
  $('provider-mode').textContent = providerLabel;
  $('provider-detail').textContent = publicDemo && data.provider.mode === 'deepseek'
    ? 'Real Plan generation'
    : data.provider.mode === 'fixture' ? 'Deterministic test provider' : 'Configured Plan provider';
  const live = data.enforcement === 'LIVE';
  sdkOnly = data.execution_path === 'sdk-only';
  const offline = live && data.armoriq?.transport === 'OFFLINE_TEST';
  $('prepare-sdk').hidden = !sdkOnly;
  $('mode-chip').textContent = publicDemo ? 'SANDBOX' : offline ? 'LOCAL / OFFLINE SDK TEST' : sdkOnly ? 'ARMORIQ SDK-ONLY LIVE' : live ? 'PROXY LIVE' : 'LOCAL / MOCK';
  $('mode-chip').dataset.mode = publicDemo ? 'sandbox' : offline ? 'offline' : live ? 'live' : 'mock';
  $('integration-status').textContent = publicDemo
    ? cloudVerified ? 'ArmorIQ Cloud · Verified' : 'ArmorIQ Cloud · Unverified'
    : live ? offline ? 'ArmorIQ · Offline test' : 'ArmorIQ · ' + (data.armoriq?.connectivity || 'Connected') : 'Not connected';
  $('integration-detail').textContent = publicDemo
    ? cloudVerified ? 'Real SDK-only Allow confirmed' : 'Evidence unavailable · no Allow claimed'
    : live ? offline ? 'No platform request was made' : 'Configured live enforcement path' : 'This runtime uses local simulated enforcement';
  $('sdk-controls').hidden = !sdkOnly;
  $('sdk-control-description').textContent = sdkOnly ? 'Explicit, ephemeral preparation. No business write.' : 'Not used by the current execution path.';
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
  capability=''; run=null; action=null; sdkStage=null; businessRecords=[]; businessRecordsLoaded=false;
  renderRun(); renderAction();
  $('capability-status').textContent = publicDemo
    ? 'Sandbox session paused. Start it again to continue. Private operator credentials are never accepted.'
    : 'Workspace locked. Load your private capability file.';
  controls();
};

$('generate').onclick = () => perform(async () => {
  const {data} = await api('/api/runs',{body:{text:$('intent').value}}); run=data; action=null; sdkStage=null;
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
  const request={body:{expected_action_version:action.version},key:crypto.randomUUID()};
  try { const {data}=await api(`/api/actions/${action.action_id}/execute`,request); action=data.action; renderAction(); await records(); }
  finally { await readStage(); }
});

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
