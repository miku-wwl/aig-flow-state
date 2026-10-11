"""OFFLINE safety tests against installed SDK 0.6.10 and the pinned public Core."""

import asyncio
import json
import time
from contextlib import contextmanager
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from agentic_intent_gate.runtime import (
    ActionCommand,
    BoundCapabilityAuthorization,
    CapabilityVerifier,
    ExecutableRegistry,
    open_runtime,
)
from armoriq_sdk import ArmorIQClient

from safeops.domain.handoff import capability_for
from safeops.integration.dispatch_permit import load_store, provision_live
from safeops.integration.sdk_only import QualificationRejected, SDKOnlyHandoffExecutor
from safeops.planning.fixture_provider import DeterministicFixtureProvider
from tests.test_runtime_integration import admitted

POLICY_ID = "c4b4d803-aefd-4c74-bc0c-dbb4564d399c"
POLICY_NAME = "cli-aegis-relay-aegis-relay-mcp"


class OfflineSDK:
    def __init__(self, fault="none"):
        self.fault, self.requests = fault, []

    def handle(self, request):
        payload = json.loads(request.content)
        self.requests.append((request.url.path, payload))
        if request.url.path == "/iap/sdk/token":
            if self.fault == "token_error":
                return httpx.Response(503, json={"message": "OFFLINE unavailable"})
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "plan_id": str(uuid4()),
                    "intent_reference": "OFFLINE",
                    "plan_hash": "OFFLINE",
                    "token": {},
                    "step_proofs": [[{"OFFLINE": True}]],
                },
            )
        if request.url.path == "/iap/sdk/enforce":
            if self.fault == "timeout":
                raise httpx.ReadTimeout("OFFLINE", request=request)
            if self.fault == "late":
                time.sleep(5.1)
            return httpx.Response(
                503 if self.fault == "non200_allow" else 200,
                json={
                    "allowed": self.fault != "deny",
                    "enforcementAction": "block"
                    if self.fault == "deny"
                    else "hold"
                    if self.fault == "hold"
                    else "allow",
                    "reason": "OFFLINE",
                    "matchedPolicy": {
                        "policyId": str(uuid4()) if self.fault == "wrong_policy" else POLICY_ID,
                        "name": POLICY_NAME,
                    },
                },
                headers={"x-request-id": str(uuid4())},
            )
        if request.url.path == "/iap/audit" or request.url.path.endswith("/status"):
            return httpx.Response(
                503 if self.fault == "report_error" else 200,
                json={"success": self.fault != "report_error"},
            )
        raise AssertionError("Unexpected OFFLINE endpoint")

    def client(self):
        sdk = ArmorIQClient(
            api_key="ak_test_offline_only",
            user_id="offline@example.test",
            agent_id="aegis-relay",
            backend_endpoint="https://api.armoriq.ai",
            max_retries=0,
            timeout=2,
            _skip_api_key_validation=True,
        )
        sdk.http_client.close()
        sdk.http_client = httpx.Client(transport=httpx.MockTransport(self.handle))
        return sdk


@contextmanager
def qualified(state, *, fault="none", no_write=False):
    provision_live(state)
    store = load_store(state)
    wire = OfflineSDK(fault)
    sdk = wire.client()
    executor = SDKOnlyHandoffExecutor(
        state,
        store,
        client=sdk,
        user_email="offline@example.test",
        policy_id=POLICY_ID,
        policy_name=POLICY_NAME,
        no_write=no_write,
    )
    identity = json.loads((state / "identity.json").read_text("utf-8"))
    verifier = CapabilityVerifier(
        (state / "capability").read_text("ascii"),
        subject_id=identity["subject_id"],
        binding=store.binding,
        operations=("read", "admit", "authorize", "execute"),
    )
    try:
        with open_runtime(
            gate_path=state / "gate.sqlite3",
            provider=DeterministicFixtureProvider(),
            capability=capability_for(store.binding),
            registry=ExecutableRegistry(executor, binding=store.binding),
            verifier=verifier,
            policy=BoundCapabilityAuthorization(
                verifier, policy_revision=identity["policy_revision"]
            ),
            predecessor_stopped=True,
        ) as runtime:
            executor.runtime = runtime
            yield runtime, store, executor, wire
    finally:
        sdk.close()


async def authorized(runtime, state):
    run, action, principal = await admitted(runtime, state)
    action = runtime.gateway.authorize(
        ActionCommand(action.action_id, action.version, str(uuid4())), principal
    ).action
    return run, action, principal


async def dispatch(runtime, action, principal):
    return await runtime.gateway.execute(
        ActionCommand(action.action_id, action.version, str(uuid4())), principal
    )


async def test_prestage_is_after_approval_and_authorization(state):
    with qualified(state) as (runtime, store, executor, wire):
        _, action, principal = await admitted(runtime, state)
        with pytest.raises(QualificationRejected, match="authorization"):
            await executor.prestage(action.action_id, principal)
        assert wire.requests == [] and store.records() == []


async def test_late_permit_durable_success_report_and_core_replay(state):
    with qualified(state) as (runtime, store, executor, wire):
        _, action, principal = await authorized(runtime, state)
        await executor.prestage(action.action_id, principal)
        assert store.records() == [] and action.state.value == "Authorized"
        assert [path for path, _ in wire.requests] == ["/iap/sdk/token"]
        command = ActionCommand(action.action_id, action.version, str(uuid4()))
        result = await runtime.gateway.execute(command, principal)
        assert result.action.state.value == "Succeeded", executor.evidence
        rows = store.records()
        assert len(rows) == 1
        assert result.action.result["receipt_reference"] == rows[0]["receipt_reference"]
        assert executor.evidence["late_permit_verified"]
        assert executor.evidence["permit_issued_after_allow"]
        assert executor.evidence["permit_remaining_ms"] > 0
        assert (await runtime.gateway.execute(command, principal)).replayed
        assert executor.business_calls == executor.calls == 1
        assert await executor.report_success() == {
            "report_http_status": 200,
            "complete_http_status": 200,
        }
        report = wire.requests[-2][1]
        assert report["plan_id"] == executor.stage.plan_id and report["step_index"] == 0
        assert report["input"] == dict(action.spec.normalized_arguments)
        assert report["output"]["receipt_reference"] == rows[0]["receipt_reference"]
        with pytest.raises(QualificationRejected):
            await executor.report_success()
        with pytest.raises(QualificationRejected):
            await executor.prestage(action.action_id, principal)


async def test_no_write_full_policy_and_permit_timing(state):
    with qualified(state, no_write=True) as (runtime, store, executor, _):
        _, action, principal = await authorized(runtime, state)
        await executor.prestage(action.action_id, principal)
        result = await dispatch(runtime, action, principal)
        assert result.action.state.value == "Failed"
        assert executor.evidence["no_write_qualified"]
        assert executor.evidence["executor_ms"] < 5000
        assert executor.business_calls == 0 and store.records() == []
        with pytest.raises(QualificationRejected):
            await executor.report_success()


@pytest.mark.parametrize("fault", ["deny", "hold", "non200_allow", "wrong_policy", "timeout"])
async def test_remote_policy_fails_closed_before_business(state, fault):
    with qualified(state, fault=fault) as (runtime, store, executor, wire):
        _, action, principal = await authorized(runtime, state)
        await executor.prestage(action.action_id, principal)
        result = await dispatch(runtime, action, principal)
        assert result.action.state.value == "Failed"
        assert executor.business_calls == 0 and store.records() == []
        assert len(wire.requests) <= 2  # hold must not create or look up a delegation
        assert not executor.evidence.get("late_permit_verified")


@pytest.mark.parametrize("mutation", ["token", "plan", "envelope", "effect_key"])
async def test_tampered_staged_identity_rejected_before_remote(state, mutation):
    with qualified(state) as (runtime, store, executor, wire):
        _, action, principal = await authorized(runtime, state)
        await executor.prestage(action.action_id, principal)
        if mutation == "token":
            executor.stage.session.current_token.raw_token["token"]["tampered"] = True
        elif mutation == "plan":
            executor.stage.session.current_token.raw_token["plan"]["steps"][0]["params"][
                "handoff_note"
            ] = "changed"
        elif mutation == "envelope":
            executor.stage = replace(executor.stage, envelope=b"changed")
        else:
            executor.stage = replace(executor.stage, effect_key=str(uuid4()))
        assert (await dispatch(runtime, action, principal)).action.state.value == "Failed"
        assert executor.business_calls == 0 and store.records() == []
        assert len(wire.requests) == 1


async def test_expired_token_is_not_refreshed_or_dispatched(state, monkeypatch):
    with qualified(state) as (runtime, store, executor, wire):
        _, action, principal = await authorized(runtime, state)
        await executor.prestage(action.action_id, principal)
        expires = executor.stage.session.current_token.expires_at
        monkeypatch.setattr("safeops.integration.sdk_only.time.time", lambda: expires + 1)
        assert (await dispatch(runtime, action, principal)).action.state.value == "Failed"
        assert executor.business_calls == 0 and store.records() == [] and len(wire.requests) == 1


async def test_late_remote_response_cannot_write_after_core_timeout(state):
    with qualified(state, fault="late") as (runtime, store, executor, wire):
        _, action, principal = await authorized(runtime, state)
        await executor.prestage(action.action_id, principal)
        assert (await dispatch(runtime, action, principal)).action.state.value == "Unknown"
        await asyncio.sleep(0.3)  # The worker only enforces policy; never performs a write.
        assert executor.business_calls == 0 and store.records() == [] and len(wire.requests) == 2


async def test_missing_stage_fails_without_network_or_business(state):
    with qualified(state) as (runtime, store, executor, wire):
        _, action, principal = await authorized(runtime, state)
        assert (await dispatch(runtime, action, principal)).action.state.value == "Failed"
        assert wire.requests == [] and store.records() == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("target", "wrong-target"),
        ("adapter_id", "wrong-adapter"),
        ("execution_scope", "420a2f02-83c5-4976-bac7-ed17a6ee7a5c"),
    ],
)
async def test_changed_core_spec_is_rejected(state, field, value, monkeypatch):
    with qualified(state) as (runtime, store, executor, wire):
        _, action, principal = await authorized(runtime, state)
        await executor.prestage(action.action_id, principal)
        execute = executor.execute

        async def changed_spec(spec, effect_key, context):
            return await execute(replace(spec, **{field: value}), effect_key, context)

        monkeypatch.setattr(executor, "execute", changed_spec)
        assert (await dispatch(runtime, action, principal)).action.state.value == "Unknown"
        # The consumer refuses the write; Core rejects the mismatched outcome identity.
        assert store.records() == [] and len(wire.requests) == 1


async def test_ambiguous_post_commit_stays_unknown_without_retry(state, monkeypatch):
    with qualified(state) as (runtime, store, executor, wire):
        _, action, principal = await authorized(runtime, state)
        await executor.prestage(action.action_id, principal)
        persist = store.persist
        monkeypatch.setattr(store, "persist", lambda *args: persist(*args, lose_ack=True))
        command = ActionCommand(action.action_id, action.version, str(uuid4()))
        result = await runtime.gateway.execute(command, principal)
        assert result.action.state.value == "Unknown"
        assert len(store.records()) == 1 and result.action.result["receipt_reference"] is None
        assert (await runtime.gateway.execute(command, principal)).replayed
        assert executor.business_calls == 1 and len(wire.requests) == 2
        with pytest.raises(QualificationRejected):
            await executor.report_success()


async def test_report_return_none_does_not_hide_http_failure(state):
    with qualified(state, fault="report_error") as (runtime, store, executor, _):
        _, action, principal = await authorized(runtime, state)
        await executor.prestage(action.action_id, principal)
        assert (await dispatch(runtime, action, principal)).action.state.value == "Succeeded"
        assert await executor.report_success() == {
            "report_http_status": 503,
            "complete_http_status": 503,
        }
        assert len(store.records()) == 1


async def test_token_failure_is_single_attempt_and_never_executes(state):
    with qualified(state, fault="token_error") as (runtime, store, executor, wire):
        _, action, principal = await authorized(runtime, state)
        with pytest.raises(Exception):  # noqa: B017
            await executor.prestage(action.action_id, principal)
        with pytest.raises(QualificationRejected):
            await executor.prestage(action.action_id, principal)
        assert len(wire.requests) == 1 and store.records() == []


async def test_permit_expiry_after_signature_verification_still_rejects(state, monkeypatch):
    with qualified(state) as (runtime, store, executor, _):
        _, action, principal = await authorized(runtime, state)
        await executor.prestage(action.action_id, principal)
        verify = executor.verifier.verify

        def expire_after_verification(args):
            spec, body = verify(args)
            monkeypatch.setattr(
                "safeops.integration.sdk_only.time.time", lambda: body["expires_at"] + 0.01
            )
            return spec, body

        monkeypatch.setattr(executor.verifier, "verify", expire_after_verification)
        assert (await dispatch(runtime, action, principal)).action.state.value == "Failed"
        assert executor.evidence["explicit_remote_allow"]
        assert executor.business_calls == 0 and store.records() == []


async def test_token_expiry_while_policy_in_flight_never_writes(state, monkeypatch):
    with qualified(state) as (runtime, store, executor, wire):
        _, action, principal = await authorized(runtime, state)
        await executor.prestage(action.action_id, principal)
        expires = executor.stage.session.current_token.expires_at

        def expire_after_response(response):
            if response.request.url.path == "/iap/sdk/enforce":
                monkeypatch.setattr("safeops.integration.sdk_only.time.time", lambda: expires + 1)

        executor.client.http_client.event_hooks["response"].append(expire_after_response)
        assert (await dispatch(runtime, action, principal)).action.state.value == "Failed"
        assert executor.evidence["explicit_remote_allow"]
        assert executor.business_calls == 0 and store.records() == [] and len(wire.requests) == 2


async def test_remote_agent_binding_cannot_change_after_stage(state):
    with qualified(state) as (runtime, store, executor, wire):
        _, action, principal = await authorized(runtime, state)
        await executor.prestage(action.action_id, principal)
        executor.client.agent_id = "wrong-agent"
        assert (await dispatch(runtime, action, principal)).action.state.value == "Failed"
        assert executor.business_calls == 0 and store.records() == [] and len(wire.requests) == 1
