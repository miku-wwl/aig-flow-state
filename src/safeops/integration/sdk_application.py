"""Application-owned ephemeral SDK stages; durable Action authority stays in Core."""

import asyncio
import logging
import os
import time
from uuid import UUID

from agentic_intent_gate.runtime import Outcome, ToolOutcome
from armoriq_sdk import ArmorIQClient
from armoriq_sdk.credentials import load_credentials

from safeops.integration.armoriq_mapping import AGENT_NAME
from safeops.integration.dispatch_permit import live_directory
from safeops.integration.live_audit import LiveAudit
from safeops.integration.sdk_only import QualificationRejected, SDKOnlyHandoffExecutor

POLICY_ID = "c4b4d803-aefd-4c74-bc0c-dbb4564d399c"
POLICY_NAME = "cli-aegis-relay-aegis-relay-mcp"
MCP_ID = "0b4133a0-9acd-451b-84a2-a795d9c593c5"
ORG_ID = "95701a09-81a7-41d8-8d8a-58d5cb83dc27"


class SDKLogRedaction(logging.Filter):
    def filter(self, record):
        # SDK errors can embed provider response bodies and user identities.
        record.msg = "ArmorIQ SDK diagnostic redacted; inspect consumer audit status."
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True


def redact_sdk_logs():
    for name in ("armoriq_sdk.client", "armoriq_sdk.session"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, SDKLogRedaction) for f in logger.filters):
            logger.addFilter(SDKLogRedaction())


def sdk_client():
    """Existing credentials only; no proxy forwarding or MCP credentials."""
    credentials = load_credentials()
    key = os.getenv("ARMORIQ_API_KEY") or (credentials.apiKey if credentials else "")
    email = os.getenv("SAFEOPS_ARMORIQ_USER_EMAIL") or (credentials.email if credentials else "")
    if not key.startswith(("ak_live_", "ak_test_")) or "@" not in email:
        raise QualificationRejected("Existing ArmorIQ credentials required")
    client = ArmorIQClient(
        api_key=key,
        user_id=email,
        agent_id=AGENT_NAME,
        timeout=2,
        max_retries=0,
        verify_ssl=True,
        backend_endpoint="https://api.armoriq.ai",
        iap_endpoint="https://iap.armoriq.ai",
        proxy_endpoint="https://proxy.armoriq.ai",
    )
    client.http_client.follow_redirects = False
    client.user_email_override = email
    return client, email


def verify_inventory(client, email):
    """Read the existing policy's target before issuing a token, outside Core's budget."""

    def guard(request):
        if (
            request.method != "POST"
            or request.url.scheme != "https"
            or request.url.host != "api.armoriq.ai"
            or request.url.path not in {"/iap/sdk/bootstrap", "/iap/sdk/resolve-user"}
            or request.url.query
        ):
            raise QualificationRejected("Unexpected inventory request")

    client.http_client.event_hooks["request"].append(guard)
    try:
        bootstrap = client.refresh_bootstrap()
        client.user_context_ttl_seconds = 0
        context = client.resolve_user(email)
        org = bootstrap.get("org") or {}
        mcps = [m for m in bootstrap.get("mcps", []) if m.get("mcpId") == MCP_ID]
        policies = [p for p in context.get("policies", []) if p.get("policyId") == POLICY_ID]
        if (
            (org.get("orgId") or org.get("id")) != ORG_ID
            or len(mcps) != 1
            or mcps[0].get("name") != "aegis-relay-mcp"
            or len(policies) != 1
        ):
            raise QualificationRejected("Registered identity mismatch")
        policy = policies[0]
        if (
            policy.get("policyName") != POLICY_NAME
            or policy.get("targetType") != "mcp_server"
            or policy.get("targetId") != MCP_ID
            or (policy.get("rules") or {}).get("allowedTools") != ["create_incident_handoff"]
            or policy.get("defaultEnforcementAction") != "block"
        ):
            raise QualificationRejected("Existing policy target mismatch")
    finally:
        client.http_client.event_hooks["request"].remove(guard)


class SDKOnlyApplication:
    mode = "LIVE"
    path = "sdk-only"

    def __init__(self, state, store, *, client_factory=None, offline_test=False):
        redact_sdk_logs()
        self.state, self.store = state, store
        self.audit = LiveAudit(live_directory(state, store) / "audit.sqlite3")
        self.client_factory = client_factory or sdk_client
        if client_factory is not None and not offline_test:
            raise QualificationRejected("Injected transport must be explicitly offline")
        self.offline_test = offline_test
        self.runtime = None
        self.stages = {}
        self.locks = {}
        self.finished = set()
        self.audit_unavailable = set()
        self.connection = "NOT_PROBED"
        self.registration = "UNVERIFIED"

    def status(self):
        return {
            "mode": "LIVE",
            "path": self.path,
            "sdk": "0.6.10",
            "transport": "OFFLINE_TEST" if self.offline_test else "REAL_PLATFORM",
            "connectivity": self.connection,
            "registration": self.registration,
        }

    def _lock(self, action_id):
        if action_id not in self.locks:
            if len(self.locks) >= 128:
                raise QualificationRejected("Session capacity reached; restart without execution")
            self.locks[action_id] = asyncio.Lock()
        return self.locks[action_id]

    def _authorized(self, action_id, principal, expected_version=None):
        UUID(action_id)
        self.runtime.gateway.require(principal, "execute")
        action = self.runtime.gateway.get(action_id, principal)
        if action.state.value != "Authorized" or (
            expected_version is not None and action.version != expected_version
        ):
            raise QualificationRejected("Exact Approved and Authorized Action required")
        return action

    def stage_status(self, action_id, principal):
        action = self.runtime.gateway.get(action_id, principal)
        executor = self.stages.get(action_id)
        status, expiry = "MISSING", None
        if action.state.value != "Authorized":
            status = (
                "NOT_AUTHORIZED" if action.state.value == "Pending" else "TERMINAL_OR_EXECUTING"
            )
        elif executor is not None:
            if executor.consumed:
                status = "CONSUMED"
            elif executor.stage is None:
                status = "PREPARING" if self._lock(action_id).locked() else "PREPARATION_FAILED"
            else:
                expiry = executor.stage.session.current_token.expires_at
                if time.time() >= expiry:
                    status = "EXPIRED"
                else:
                    try:
                        executor._validate(executor.stage)
                        status = "READY"
                    except Exception:
                        status = "INVALID"
        try:
            events = [e for e in self.audit.events() if e["action_id"] == action_id]
        except Exception:
            events = []
            self.audit_unavailable.add(action_id)
        # Closed response metadata only; never return tokens or provider bodies.
        policy = None
        candidates = []
        if executor is not None:
            candidates.append((executor.events, executor.evidence, self.status()["transport"]))
        candidates.extend(
            (
                event.get("diagnostics", {}).get("http_events", []),
                event.get("diagnostics", {}).get("execution", {}),
                event.get("diagnostics", {}).get("transport"),
            )
            for event in reversed(events)
        )
        for http_events, evidence, transport in candidates:
            enforced = [e for e in http_events if e["phase"] == "ENFORCE"]
            if len(enforced) == 1:
                response = enforced[0]
                policy = {
                    "transport": transport,
                    "tool": action.spec.tool_name,
                    "action": response.get("action"),
                    "policy_id": response.get("policy_id"),
                    "policy_name": response.get("policy_name"),
                    "server_request_id": response.get("server_request_id"),
                    "explicit_allow_confirmed": evidence.get("explicit_remote_allow") is True,
                }
                break
        return {
            "action_id": action_id,
            "status": status,
            "expires_at": expiry,
            "plan_id": executor.stage.plan_id if executor and executor.stage else None,
            "audit": events[-1] if events else None,
            "policy": policy,
            "audit_storage": "UNAVAILABLE" if action_id in self.audit_unavailable else "AVAILABLE",
            "tokens_in_memory_only": True,
        }

    def require_ready(self, action_id, principal):
        self._authorized(action_id, principal)
        if self.stage_status(action_id, principal)["status"] != "READY":
            raise QualificationRejected("SDK stage missing, invalid or expired; prepare explicitly")

    async def prepare(self, action_id, principal, expected_version):
        self._authorized(action_id, principal, expected_version)
        lock = self._lock(action_id)
        if lock.locked():
            raise QualificationRejected("Preparation already in progress")
        async with lock:
            self._authorized(action_id, principal, expected_version)
            previous = self.stages.get(action_id)
            if previous:
                status = self.stage_status(action_id, principal)["status"]
                if status == "READY":
                    return self.stage_status(action_id, principal)
                if status != "EXPIRED" or previous.consumed:
                    raise QualificationRejected("Preparation cannot be retried in this session")
                previous.close()
            client, email = await asyncio.to_thread(self.client_factory)
            try:
                await asyncio.to_thread(verify_inventory, client, email)
                self.registration = "EXISTING_TARGET_VERIFIED"
                executor = SDKOnlyHandoffExecutor(
                    self.state,
                    self.store,
                    client=client,
                    user_email=email,
                    policy_id=POLICY_ID,
                    policy_name=POLICY_NAME,
                    no_write=False,
                )
                executor.runtime = self.runtime
                self.stages[action_id] = executor
                await executor.prestage(action_id, principal)
                self.connection = "TOKEN_HTTP_200"
            except BaseException:
                client.close()
                # Token request failure is not automatically retried or refreshed.
                raise
            self.audit.record(
                "SDK_PRESTAGED",
                action_id=action_id,
                effect_key=executor.stage.effect_key,
                plan_id=executor.stage.plan_id,
                diagnostics={"path": self.path, "prestage_ms": executor.evidence["prestage_ms"]},
            )
            return self.stage_status(action_id, principal)

    async def execute(self, spec, effect_key, context):
        candidates = [
            e for e in self.stages.values() if e.stage and e.stage.effect_key == effect_key
        ]
        if len(candidates) != 1:
            return ToolOutcome(
                Outcome.CONFIRMED_FAILURE,
                effect_key,
                spec.execution_scope,
                spec.target,
                spec.payload_digest(),
                None,
                "INPUT_REJECTED",
            )
        return await candidates[0].execute(spec, effect_key, context)

    async def finalize(self, action_id, principal):
        """Outside Core execution; never repeat a business effect or report on replay."""
        executor = self.stages.get(action_id)
        if executor is None or not executor.consumed:
            return
        async with self._lock(action_id):
            if action_id in self.finished or executor.lifecycle_started:
                return
            action = self.runtime.gateway.get(action_id, principal)
            if action.state.value not in {"Succeeded", "Failed", "Unknown"}:
                return
            self.finished.add(action_id)
            try:
                await self._finish(action, executor)
            except Exception:
                self.audit_unavailable.add(action_id)
                executor.lifecycle_started = True
                executor.close()

    async def _finish(self, action, executor):
        action_id = action.action_id
        diagnostics = {
            "path": self.path,
            "transport": self.status()["transport"],
            "execution": dict(executor.evidence),
            "http_events": list(executor.events),
        }
        self.audit.record(
            "SDK_" + action.state.value.upper(),
            action_id=action_id,
            effect_key=action.effect_key,
            plan_id=executor.stage.plan_id,
            receipt_reference=(action.result or {}).get("receipt_reference"),
            diagnostics=diagnostics,
        )
        if action.state.value != "Succeeded":
            executor.lifecycle_started = True
            executor.close()
            return
        self.audit.record(
            "SDK_AUDIT_REPORT_STARTED",
            action_id=action_id,
            effect_key=action.effect_key,
            plan_id=executor.stage.plan_id,
            receipt_reference=action.result["receipt_reference"],
        )
        try:
            result = await executor.report_success()
            reports = [e for e in executor.events if e["phase"] == "REPORT"]
            completed = [e for e in executor.events if e["phase"] == "COMPLETE"]
            acknowledged = (
                result["report_http_status"] == result["complete_http_status"] == 200
                and len(reports) == len(completed) == 1
                and reports[0].get("audit_id") is not None
                and completed[0].get("success") is True
                and completed[0].get("plan_id") == executor.stage.plan_id
            )
            classification = (
                "SDK_AUDIT_POST_ACKNOWLEDGED" if acknowledged else "SDK_AUDIT_UNVERIFIED"
            )
            diagnostics["lifecycle"] = result
        except Exception:
            classification = "SDK_AUDIT_UNVERIFIED"
        finally:
            # Even a reporting exception cannot cause another business write/report.
            executor.lifecycle_started = True
            executor.close()
        diagnostics["http_events"] = list(executor.events)
        self.audit.record(
            classification,
            action_id=action_id,
            effect_key=action.effect_key,
            plan_id=executor.stage.plan_id,
            receipt_reference=action.result["receipt_reference"],
            diagnostics=diagnostics,
        )

    def close(self):
        for executor in self.stages.values():
            executor.close()
