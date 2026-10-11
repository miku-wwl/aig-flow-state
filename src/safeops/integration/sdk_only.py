"""Opt-in SDK-only qualification adapter; Core still owns every Action transition.

Remote Allow gates the tool only. Exact parameters and the late dispatch permit
are verified locally. This module does not change the app's MOCK/proxy modes.
"""

import asyncio
import hashlib
import json
import math
import time
from dataclasses import dataclass
from uuid import UUID

from agentic_intent_gate.runtime import (
    EXTERNAL_PAYLOAD_REVISION,
    ExecutionSpec,
    Outcome,
    ToolOutcome,
)
from armoriq_sdk.observability import ObservabilityConfig
from armoriq_sdk.session import ReportOptions, SessionOptions

from safeops.domain.handoff import valid_arguments
from safeops.execution.handoff_store import binding_identity
from safeops.integration.armoriq_mapping import AGENT_NAME, MCP_NAME
from safeops.integration.dispatch_permit import (
    PermitIssuer,
    PermitVerifier,
    canonical,
    live_directory,
)


class QualificationRejected(ValueError):
    pass


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class StagedPlan:
    action_id: str
    effect_key: str
    envelope: bytes
    plan: bytes
    token_digest: str
    plan_id: str
    session: object


class ExecutionDeadline:
    def __init__(self, context, expires_at):
        self.context, self.expires_at = context, expires_at

    def expired(self):
        return self.context.expired() or time.time() >= self.expires_at


class SDKOnlyHandoffExecutor:
    """One reviewed Action per instance, no token refresh and no automatic retry.

    Trusted startup must attach the public runtime and supply the independently
    verified existing policy ID/name. HTTP hooks check the *actual* SDK exchange;
    a session's parsed allowed flag alone is insufficient.
    """

    mode = "LIVE"

    def close(self):
        self.client.close()

    def __init__(self, state, store, *, client, user_email, policy_id, policy_name, no_write=True):
        UUID(policy_id)
        if not policy_name or not user_email or client.agent_id != AGENT_NAME:
            raise QualificationRejected("Trusted policy and user identity required")
        directory = live_directory(state, store)
        self.store, self.client, self.user_email = store, client, user_email
        self.policy_id, self.policy_name, self.no_write = policy_id, policy_name, no_write
        self.issuer, self.verifier = (
            PermitIssuer(directory, store),
            PermitVerifier(directory, store),
        )
        self.runtime = None
        self.stage = None
        self.started = False
        self.consumed = False
        self.lifecycle_started = False
        self.calls = 0
        self.business_calls = 0
        self.events = []
        self.evidence = {}
        self._wire_phase = None
        self._expected_request = None
        self._context = None
        self.client.http_client.follow_redirects = False
        self.client.http_client.event_hooks["request"].append(self._before_request)
        self.client.http_client.event_hooks["response"].append(self._after_response)

    def _before_request(self, request):
        expected_path = {
            "TOKEN": "/iap/sdk/token",
            "ENFORCE": "/iap/sdk/enforce",
            "REPORT": "/iap/audit",
            "COMPLETE": f"/iap/plans/{self.stage.plan_id}/status" if self.stage else None,
        }.get(self._wire_phase)
        if (
            request.method != "POST"
            or request.url.scheme != "https"
            or request.url.host != "api.armoriq.ai"
            or request.url.port not in (None, 443)
            or request.url.path != expected_path
            or request.url.query
        ):
            raise QualificationRejected("Unapproved SDK request")
        payload = json.loads(request.content)
        if self._wire_phase == "TOKEN":
            if (
                payload.get("plan") != self._expected_request
                or payload.get("user_email") != self.user_email
                or payload.get("agent_id") != AGENT_NAME
            ):
                raise QualificationRejected("Token request changed the approved plan")
        elif self._wire_phase == "ENFORCE":
            if payload != self._expected_request:
                raise QualificationRejected("Enforcement request changed")
            remaining = self._context.deadline - time.monotonic() - 0.5
            if self._context.cancelled.is_set() or remaining <= 0:
                raise QualificationRejected("Enforcement budget exhausted")
            # SDK 0.6.10 otherwise hard-codes a ten-second network timeout.
            request.extensions["timeout"] = dict.fromkeys(
                ("connect", "read", "write", "pool"), min(2.0, remaining)
            )
        elif self._wire_phase == "REPORT":
            if any(payload.get(k) != v for k, v in self._expected_request.items()):
                raise QualificationRejected("Audit attribution changed")
        elif self._wire_phase == "COMPLETE" and payload != {"status": "completed"}:
            raise QualificationRejected("Plan completion changed")
        request.extensions["aegis_phase"] = self._wire_phase
        request.extensions["aegis_started"] = time.perf_counter()
        request.extensions["aegis_digest"] = hashlib.sha256(request.content).hexdigest()

    def _after_response(self, response):
        response.read()
        request = response.request
        phase = request.extensions.get("aegis_phase")
        if not phase:
            return
        event = {
            "phase": phase,
            "path": request.url.path,
            "http_status": response.status_code,
            "elapsed_ms": round(
                (time.perf_counter() - request.extensions["aegis_started"]) * 1000, 3
            ),
            "request_sha256": request.extensions["aegis_digest"],
            "response_sha256": hashlib.sha256(response.content).hexdigest(),
            "server_request_id": safe_uuid(response.headers.get("x-request-id")),
            "server_date": response.headers.get("date"),
        }
        if phase == "ENFORCE":
            try:
                raw = response.json()
            except ValueError:
                raw = {}
            policy = raw.get("matchedPolicy") or {}
            event.update(
                allowed=raw.get("allowed") is True,
                action=raw.get("enforcementAction")
                if raw.get("enforcementAction") in {"allow", "block", "deny", "hold"}
                else None,
                reason=raw.get("reason")
                if raw.get("reason") in {"tool_not_in_allowlist", "OFFLINE"}
                else "REMOTE_REASON_REDACTED",
                policy_id=safe_uuid(policy.get("policyId")),
                policy_name=policy.get("name") if policy.get("name") == self.policy_name else None,
            )
        elif phase in {"REPORT", "COMPLETE"}:
            try:
                raw = response.json()
            except ValueError:
                raw = {}
            if isinstance(raw, dict):
                event.update(
                    audit_id=safe_uuid(raw.get("id") or raw.get("audit_id") or raw.get("auditId")),
                    plan_id=safe_uuid(raw.get("plan_id") or raw.get("planId")),
                    success=raw.get("success") if type(raw.get("success")) is bool else None,
                )
        self.events.append(event)

    def _envelope(self, action):
        if not action.authorization:
            raise QualificationRejected("Independent authorization missing")
        run = self.runtime.run_service.get(action.spec.run_id)
        spec = ExecutionSpec.from_compiled(action.spec)
        if (
            run.state.value != "Approved"
            or run.run_id != action.spec.run_id
            or run.version != action.spec.approved_run_version
            or run.plan is None
            or len(run.plan.steps) != 1
            or not self.store.binding.matches(spec)
            or spec.identity_revision != EXTERNAL_PAYLOAD_REVISION
            or not valid_arguments(dict(spec.arguments))
            or run.plan.to_dict()["steps"][0]["arguments"] != dict(spec.arguments)
        ):
            raise QualificationRejected("Reviewed Plan or trusted binding mismatch")
        return canonical(
            {
                "action_id": action.action_id,
                "effect_key": action.effect_key,
                "compiled_spec": action.spec.to_dict(),
                "authorization": dict(action.authorization),
                "reviewed_run": run.to_dict(),
                "binding": vars(self.store.binding),
                "store_id": self.store.store_id,
                "payload_digest": spec.payload_digest(),
                "remote_policy": {
                    "policy_id": self.policy_id,
                    "policy_name": self.policy_name,
                    "mcp": MCP_NAME,
                    "agent": self.client.agent_id,
                    "user_email": self.user_email,
                },
            }
        )

    def _validate(self, stage, spec=None, context=None):
        action = self.runtime.actions.get(stage.action_id)
        expected_state = "Executing" if context is not None else "Authorized"
        if (
            action is None
            or action.state.value != expected_state
            or action.effect_key != stage.effect_key
            or self._envelope(action) != stage.envelope
            or (spec is not None and ExecutionSpec.from_compiled(action.spec) != spec)
            or (context is not None and context.expired())
        ):
            raise QualificationRejected("Core context changed or expired")
        session, token = stage.session, stage.session.current_token
        if (
            session.current_mode != "sdk"
            or session.user_email != self.user_email
            or token is None
            or token.plan_id != stage.plan_id
            or digest(token.model_dump()) != stage.token_digest
            or not math.isfinite(token.expires_at)
            or time.time() >= token.expires_at
            or canonical(token.raw_token.get("plan")) != stage.plan
        ):
            raise QualificationRejected("Staged token changed or expired")
        return action

    async def prestage(self, action_id, principal):
        if self.started or self.runtime is None:
            raise QualificationRejected("Stage is single-use")
        action = self.runtime.gateway.get(action_id, principal)
        if action.state.value != "Authorized":
            raise QualificationRejected("Stage requires exact approval and authorization")
        envelope = self._envelope(action)
        spec = ExecutionSpec.from_compiled(action.spec)
        # Burn the opportunity before the request; a failed token call is never retried.
        self.started = True
        self.store.validate()
        session = self.client.for_user(self.user_email).start_session(
            SessionOptions(
                mode="sdk",
                default_mcp_name=MCP_NAME,
                validity_seconds=10,
                llm="core-reviewed-plan",
                observability=ObservabilityConfig(enabled=False),
            )
        )
        goal = "Core-approved and independently authorized handoff: " + envelope.decode()
        plan = {
            "goal": goal,
            "steps": [
                {
                    "action": spec.tool_name,
                    "tool": spec.tool_name,
                    "mcp": MCP_NAME,
                    "params": dict(spec.arguments),
                    "description": f"Call {spec.tool_name} on {MCP_NAME}",
                }
            ],
        }
        self._wire_phase, self._expected_request = "TOKEN", plan
        before = time.perf_counter()
        try:
            token = await asyncio.to_thread(
                session.start_plan,
                [{"name": f"{MCP_NAME}__{spec.tool_name}", "args": dict(spec.arguments)}],
                goal=goal,
            )
        finally:
            self.evidence["prestage_ms"] = round((time.perf_counter() - before) * 1000, 3)
            self._wire_phase = None
        events = [e for e in self.events if e["phase"] == "TOKEN"]
        if len(events) != 1 or events[0]["http_status"] != 200:
            raise QualificationRejected("Token issuance not confirmed")
        UUID(token.plan_id)
        stage = StagedPlan(
            action_id,
            action.effect_key,
            envelope,
            canonical(plan),
            digest(token.model_dump()),
            token.plan_id,
            session,
        )
        self._validate(stage)
        self.stage = stage
        self.evidence.update(
            action_id=action_id,
            effect_key=action.effect_key,
            plan_id=token.plan_id,
            envelope_sha256=hashlib.sha256(envelope).hexdigest(),
            payload_digest=spec.payload_digest(),
            prestaged_before_core_claim=True,
        )
        return {key: self.evidence[key] for key in self.evidence}

    async def execute(self, spec, effect_key, context):
        self.calls += 1
        started = time.perf_counter()
        write_started = False

        def outcome(category, receipt=None):
            return ToolOutcome(
                category,
                effect_key,
                spec.execution_scope,
                spec.target,
                spec.payload_digest(),
                receipt,
                "INPUT_REJECTED" if category == Outcome.CONFIRMED_FAILURE else None,
            )

        try:
            if self.stage is None or self.consumed or self.stage.effect_key != effect_key:
                raise QualificationRejected("No unused exact stage")
            self.consumed = True
            stage = self.stage
            self._validate(stage, spec, context)
            token = stage.session.current_token
            args = dict(spec.arguments)
            self._expected_request = {
                "tool": spec.tool_name,
                "arguments": args,
                "intent_token": token.raw_token,
                "policy_snapshot": token.policy_snapshot,
                "user_email": self.user_email,
                "agent_id": self.client.agent_id,
            }
            self._context, self._wire_phase = context, "ENFORCE"
            before = time.perf_counter()
            decision = await asyncio.to_thread(
                stage.session.check,
                f"{MCP_NAME}__{spec.tool_name}",
                args,
                user_email=self.user_email,
            )
            self.evidence["enforcement_ms"] = round((time.perf_counter() - before) * 1000, 3)
            self._wire_phase = None
            events = [e for e in self.events if e["phase"] == "ENFORCE"]
            explicit_allow = (
                len(events) == 1
                and events[0]["http_status"] == 200
                and events[0]["allowed"]
                and events[0]["action"] == "allow"
                and events[0]["policy_id"] == self.policy_id
                and events[0]["policy_name"] == self.policy_name
                and decision.allowed is True
                and decision.action == "allow"
            )
            self.evidence["explicit_remote_allow"] = explicit_allow
            if not explicit_allow:
                raise QualificationRejected("Explicit remote Allow not confirmed")
            self._validate(stage, spec, context)
            # Late issuance, after remote Allow, using the existing signed permit contract.
            self.issuer.runtime = self.runtime
            self.issuer.track(stage.action_id)
            permit = self.issuer.issue(spec, effect_key, context)
            verified, body = self.verifier.verify({**args, "_dispatch": permit})
            if (
                verified != spec
                or body["action_id"] != stage.action_id
                or body["effect_key"] != effect_key
                or body["attempt_id"] != context.attempt_id
            ):
                raise QualificationRejected("Late dispatch context mismatch")
            deadline = ExecutionDeadline(context, body["expires_at"])
            self._validate(stage, spec, context)
            if deadline.expired():
                raise QualificationRejected("Dispatch expired")
            self.evidence.update(
                late_permit_verified=True,
                permit_sha256=digest(permit),
                permit_issued_after_allow=True,
                permit_remaining_ms=round((body["expires_at"] - time.time()) * 1000, 3),
                core_remaining_ms=round(
                    (context.deadline - asyncio.get_running_loop().time()) * 1000, 3
                ),
            )
            if self.no_write:
                self.evidence["no_write_qualified"] = True
                return outcome(Outcome.CONFIRMED_FAILURE)
            write_started = True
            self.business_calls += 1
            before = time.perf_counter()
            receipt = self.store.persist(spec, effect_key, deadline)
            self.evidence["durable_write_ms"] = round((time.perf_counter() - before) * 1000, 3)
            rows = [row for row in self.store.records() if row["effect_key"] == effect_key]
            if (
                len(rows) != 1
                or rows[0]["receipt_reference"] != receipt
                or rows[0]["payload_digest"] != spec.payload_digest()
                or rows[0]["store_id"] != self.store.store_id
                or rows[0]["binding_identity"] != binding_identity(self.store.binding)
                or any(rows[0][name] != value for name, value in args.items())
                or deadline.expired()
            ):
                raise QualificationRejected("Durable receipt verification failed")
            self.evidence.update(receipt_reference=receipt, durable_record_verified=True)
            return outcome(Outcome.SUCCESS, receipt)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.evidence["failure_type"] = type(exc).__name__
            return outcome(Outcome.UNKNOWN_OUTCOME if write_started else Outcome.CONFIRMED_FAILURE)
        finally:
            self._wire_phase = None
            self.evidence["executor_ms"] = round((time.perf_counter() - started) * 1000, 3)

    async def report_success(self):
        """Post-Core lifecycle only; acknowledgements are not audit persistence proof."""
        if self.lifecycle_started or self.no_write or not self.stage:
            raise QualificationRejected("No fresh successful business execution to report")
        action = self.runtime.actions.get(self.stage.action_id)
        if (
            action.state.value != "Succeeded"
            or self._envelope(action) != self.stage.envelope
            or not self.evidence.get("durable_record_verified")
            or action.result["receipt_reference"] != self.evidence["receipt_reference"]
        ):
            raise QualificationRejected("Core success and receipt required")
        self.lifecycle_started = True
        result = {
            "action_id": action.action_id,
            "effect_key": action.effect_key,
            "payload_digest": self.evidence["payload_digest"],
            "receipt_reference": self.evidence["receipt_reference"],
            "core_state": "Succeeded",
        }
        self._wire_phase = "REPORT"
        self._expected_request = {
            "plan_id": self.stage.plan_id,
            "step_index": 0,
            "action": action.spec.tool_name,
            "tool": action.spec.tool_name,
            "mcp": MCP_NAME,
            "input": dict(action.spec.normalized_arguments),
            "output": result,
            "status": "success",
            "user_email": self.user_email,
        }
        try:
            await asyncio.to_thread(
                self.stage.session.report,
                f"{MCP_NAME}__{action.spec.tool_name}",
                dict(action.spec.normalized_arguments),
                result,
                ReportOptions(status="success", duration_ms=self.evidence["executor_ms"]),
            )
            self._wire_phase = "COMPLETE"
            await asyncio.to_thread(self.client.complete_plan, self.stage.plan_id)
        finally:
            self._wire_phase = None
        return {
            phase.lower() + "_http_status": next(
                (e["http_status"] for e in self.events if e["phase"] == phase), None
            )
            for phase in ("REPORT", "COMPLETE")
        }


def safe_uuid(value):
    try:
        return str(UUID(value)) if isinstance(value, str) and str(UUID(value)) == value else None
    except (ValueError, TypeError, AttributeError):
        return None
