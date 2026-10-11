'use strict';
const $ = id => document.getElementById(id);
let capability = '', run = null, action = null, lastExecution = null, busy = false, scope = null;
const buttons = ['generate','approve','reject','admit','authorize','execute','try-unauthorized','replay','restore','refresh-records','policy-test'];
function controls() {
  buttons.forEach(id => $(id).disabled = busy || !capability);
  ['approve','reject'].forEach(id => $(id).disabled ||= run?.state !== 'AwaitingApproval');
  $('admit').disabled ||= run?.state !== 'Approved' || !!action;
  $('authorize').disabled ||= action?.state !== 'Pending';
  $('execute').disabled ||= action?.state !== 'Authorized';
  $('try-unauthorized').disabled ||= action?.state !== 'Pending';
  $('replay').disabled ||= !lastExecution;
}
function message(id, text) { $(id).textContent = text; $(id).hidden = !text; }
async function api(path, {body, key, expectedError = false} = {}) {
  const headers = {};
  if (capability) headers.Authorization = 'Bearer ' + capability;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (key) headers['Idempotency-Key'] = key;
  const response = await fetch(path, {method:body === undefined ? 'GET':'POST', headers, body:body === undefined ? undefined : JSON.stringify(body), cache:'no-store', credentials:'omit'});
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
function renderRun() {
  $('run-state').textContent = run?.state || 'No Run selected';
  $('run-version').textContent = run ? `Version ${run.version}` : '';
  $('run-id').textContent = run ? `Run ${run.run_id}` : '';
  $('restore-id').value = run?.run_id || '';
  $('plan-json').textContent = run?.plan ? JSON.stringify(run.plan,null,2) : 'No validated Plan.';
  $('validation').textContent = run?.plan ? `Validated by the shared Runtime · Risk: ${run.risk_class}` : run?.error ? `${run.error.code}: ${run.error.message}` : 'Generate a Plan to see validation and risk.';
  $('plan-fields').replaceChildren();
  if (run?.plan) {
    const args = run.plan.steps[0].arguments;
    Object.entries({'Goal':run.plan.goal,'Target':run.plan.target,'Tool':run.plan.steps[0].tool_name,'Incident':args.incident_id,'Summary':args.summary,'Handoff note':args.handoff_note}).forEach(([name,value]) => {
      const dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent=name; dd.textContent=value; $('plan-fields').append(dt,dd);
    });
  }
}
function renderAction() {
  $('action-state').textContent = action?.state || 'No Action admitted';
  $('action-id').textContent = action ? `Action ${action.action_id} · Version ${action.version}` : '';
  $('receipt').textContent = action?.result?.receipt_reference || '—';
  $('action-json').textContent = action ? JSON.stringify(action,null,2) : 'No Action yet.';
  const explanations = {Pending:'Approval is recorded. Independent authorization is still required.',Authorized:'Authorization is recorded. Execute only when ready.',Succeeded:'Confirmed durable handoff. Match this receipt with the business record below.',Failed:'No-effect failure confirmed. Inspect policy evidence if applicable.',Unknown:'Outcome unknown: a handoff may exist. No automatic retry or redispatch is permitted.',Executing:'Backend execution is in progress; refresh only reads state.'};
  $('action-message').textContent = explanations[action?.state] || 'Awaiting your review.';
}
async function records() {
  const {data} = await api('/api/handoffs'); $('records').replaceChildren();
  if (!data.records.length) { const p=document.createElement('p'); p.className='empty'; p.textContent='No handoff records yet.'; $('records').append(p); }
  data.records.forEach(record => {
    const item=document.createElement('article'); item.className='record'; item.dataset.receipt=record.receipt_reference;
    [['strong',record.incident_id + ' · ' + record.summary],['p',record.handoff_note],['p','Receipt ' + record.receipt_reference],['p','Effect ' + record.effect_key + ' · ' + record.created_at]].forEach(([tag,text],index) => {const child=document.createElement(tag); child.textContent=text; if(index>=2)child.className='identifier'; item.append(child);}); $('records').append(item);
  });
  const evidence = await api('/api/policy/evidence');
  const latest = evidence.data.events.at(-1);
  $('live-evidence').textContent = evidence.data.mode === 'LIVE' && latest ? `${latest.status} · Action ${latest.action_id || 'canary'} · Plan ${latest.plan_id || 'unavailable'} · Receipt ${latest.receipt_reference || 'unconfirmed'}` : '';
}
async function loadRun(id) {
  const {data} = await api('/api/runs/' + encodeURIComponent(id)); run=data;
  localStorage.setItem('safeops-run-' + scope,run.run_id); renderRun();
  const actions = await api(`/api/runs/${run.run_id}/actions`); action=actions.data.actions[0] || null; lastExecution=null; renderAction();
}
async function updateStatus() {
  const {data} = await api('/api/status'); scope=data.execution_scope;
  $('provider-mode').textContent = data.provider.mode === 'fixture' ? 'Deterministic fixture · offline' : `Live local Ollama · ${data.provider.model || 'discover phi4-mini'}`;
  const live = data.enforcement === 'LIVE';
  const offline = live && data.armoriq.transport === 'OFFLINE_TEST';
  $('mode-chip').textContent = offline ? 'LOCAL / OFFLINE SDK TEST' : live ? 'LOCAL / LIVE ARMORIQ' : 'LOCAL / MOCK';
  $('enforcement-mode').textContent = data.enforcement_label;
  $('integration-status').textContent = live ? `Connectivity: ${data.armoriq.connectivity} · Registration: ${data.armoriq.registration}` : 'Local single-operator demo · Synthetic incidents only';
  $('policy-lab-label').textContent = offline ? 'OFFLINE POLICY TEST' : live ? 'LIVE POLICY BOUNDARY' : 'MOCK POLICY LAB';
  $('policy-lab-description').textContent = live ? 'Probe purge_incident_history with a separate valid ArmorIQ intent. Only an explicit policy denial proves this boundary.' : 'Request purge_incident_history against a deterministic local deny policy.';
  $('policy-test').textContent = offline ? 'Test offline forbidden-operation response' : live ? 'Test real forbidden-operation policy' : 'Test simulated forbidden operation';
  $('mode-footer').textContent = `Agentic Intent Gate v0.1.0 · One trusted SIDE_EFFECT tool · ${offline ? 'Offline SDK transport — no cloud qualification' : live ? 'Real ArmorIQ mode — verify policy and audit evidence' : 'Mock ArmorIQ mode'}`;
  return data;
}
$('capability-file').addEventListener('change', () => perform(async () => {
  const input=$('capability-file'), file=input.files[0]; if(!file)return;
  try { if(file.size>128)throw new Error('Choose the private capability file created by safeops init.'); const text=(await file.text()).trim(); if(!/^[0-9a-f]{64}$/.test(text))throw new Error('Invalid capability file.'); capability=text; }
  finally { input.value=''; }
  try { await updateStatus(); await records(); const remembered=localStorage.getItem('safeops-run-' + scope); if(remembered)await loadRun(remembered); }
  catch(error) { capability=''; throw error; }
  $('capability-status').textContent='Workspace unlocked. Capability remains only in memory; reload it after refresh.';
}));
$('lock').onclick = () => { capability=''; run=null; action=null; lastExecution=null; renderRun(); renderAction(); $('records').replaceChildren(); $('policy-result').textContent='No policy test yet.'; $('capability-status').textContent='Workspace locked. Load your private capability file.'; controls(); };
$('generate').onclick = () => perform(async () => {
  const {data} = await api('/api/runs',{body:{text:$('intent').value}}); run=data; action=null; lastExecution=null;
  localStorage.setItem('safeops-run-' + scope,run.run_id); renderRun(); renderAction();
  const status=await updateStatus();
  if(run.error) { throw new Error(`${run.error.code}: ${run.error.message}${status.provider.last_error ? ' · ' + status.provider.last_error : ''}`); }
  message('notice','Plan validated and Run persisted. Review it before approving.');
});
for (const [id,decision] of [['approve','APPROVE'],['reject','REJECT']]) $(id).onclick = () => perform(async () => {
  const {data}=await api(`/api/runs/${run.run_id}/approval`,{body:{decision,expected_version:run.version}}); run=data; renderRun(); message('notice',decision==='APPROVE' ? 'Exact Plan approved. Admit the Action, then authorize it separately.' : 'Plan rejected. No Action executed.');
});
$('admit').onclick = () => perform(async () => {const {data}=await api(`/api/runs/${run.run_id}/actions`,{body:{expected_run_version:run.version},key:crypto.randomUUID()}); action=data.actions[0]; renderAction();});
$('authorize').onclick = () => perform(async () => {const {data}=await api(`/api/actions/${action.action_id}/authorize`,{body:{expected_action_version:action.version},key:crypto.randomUUID()}); action=data.action; renderAction();});
$('execute').onclick = () => perform(async () => {
  lastExecution={path:`/api/actions/${action.action_id}/execute`,body:{expected_action_version:action.version},key:crypto.randomUUID()};
  const {data}=await api(lastExecution.path,lastExecution); action=data.action; renderAction(); await records();
});
$('replay').onclick = () => perform(async () => {const {data}=await api(lastExecution.path,lastExecution); action=data.action; renderAction(); await records(); message('notice',data.replayed ? 'Exact request replayed. The durable receipt is unchanged.' : 'Backend execution result received.');});
$('try-unauthorized').onclick = () => perform(async () => {
  const {response,data}=await api(`/api/actions/${action.action_id}/execute`,{body:{expected_action_version:action.version},key:crypto.randomUUID(),expectedError:true});
  if(response.ok)throw new Error('Unexpected allowed execution'); message('error',`${data.error.code}: ${data.error.message} · No business effect.`); await records();
});
$('policy-test').onclick = () => perform(async () => {
  const {data}=await api('/api/policy/test',{body:{operation:'purge_incident_history'},expectedError:true}); $('policy-result').textContent=JSON.stringify(data,null,2); await records();
});
$('restore').onclick = () => perform(() => loadRun($('restore-id').value.trim()));
$('refresh-records').onclick = () => perform(records);
controls(); updateStatus().catch(error => message('error',error.message));
