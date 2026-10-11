import asyncio
import copy
import json
import time
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agentic_intent_gate.runtime import ActionCommand
from fastapi.testclient import TestClient

from safeops.integration.armoriq_mapping import captured_step
from safeops.integration.dispatch_permit import (
    PermitIssuer,
    canonical,
    load_store,
    provision_live,
)
from safeops.integration.live_armoriq import build_client
from safeops.integration.runtime_composition import composition
from safeops.main import create_app
from safeops.mcp.server import create_mcp_app
from tests.armoriq_harness import offline_live
from tests.conftest import approved_action, command_headers
from tests.test_handoff_executor import context, execution_spec
from tests.test_runtime_integration import admitted


def test_client_credentials_and_no_fallback(state, monkeypatch):
    provision_live(state)
    monkeypatch.setattr("safeops.integration.live_armoriq.load_credentials", lambda: None)
    monkeypatch.delenv("ARMORIQ_API_KEY", raising=False)
    monkeypatch.delenv("SAFEOPS_ARMORIQ_USER_EMAIL", raising=False)
    with pytest.raises(ValueError, match="existing ArmorIQ credentials"):
        build_client(state / "armoriq")
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(http_client=SimpleNamespace(follow_redirects=True))

    monkeypatch.setenv("ARMORIQ_API_KEY", "ak_test_offline_only")
    monkeypatch.setenv("SAFEOPS_ARMORIQ_USER_EMAIL", "offline@example.test")
    client, _ = build_client(state / "armoriq", factory=factory)
    assert captured["max_retries"] == 0 and captured["verify_ssl"] is True
    assert captured["agent_id"] == "aegis-relay" and client.user_email_override
    assert set(captured["mcp_credentials"]) == {"aegis-relay-mcp"}
    assert client.http_client.follow_redirects is False


def test_real_mode_requires_explicit_private_setup(settings):
    with pytest.raises(FileNotFoundError), composition(replace(settings, enforcement_mode="real")):
        pass


@pytest.mark.parametrize(
    "fault,state_name,effects",
    [
        ("none", "Succeeded", 1),
        ("deny", "Failed", 0),
        ("hold", "Failed", 0),
        ("mismatch", "Failed", 0),
        ("token_failure", "Failed", 0),
        ("timeout", "Unknown", 0),
        ("remote_5xx", "Unknown", 0),
        ("missing_receipt", "Unknown", 0),
        ("wrong_receipt", "Unknown", 1),
        ("wrong_digest", "Unknown", 1),
        ("wrong_action", "Unknown", 1),
        ("lost_ack", "Unknown", 1),
        ("timeout_after_commit", "Unknown", 1),
    ],
)
def test_actual_sdk_offline_forwarding_and_recovery(settings, state, fault, state_name, effects):
    offline = offline_live(state, fault=fault)
    live_settings = replace(settings, enforcement_mode="real")
    app = create_app(live_settings, enforcement=offline.live)
    headers = {"Authorization": "Bearer " + (state / "capability").read_text("ascii")}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        _, action = approved_action(client)
        key = command_headers()
        request = {"expected_action_version": action["version"]}
        url = f"/api/actions/{action['action_id']}/execute"
        first = client.post(url, headers=key, json=request)
        assert first.status_code == 200, first.text
        result = first.json()["action"]
        assert result["state"] == state_name
        assert len(client.get("/api/handoffs").json()["records"]) == effects
        replay = client.post(url, headers=key, json=request).json()
        assert replay["replayed"] and replay["action"] == result
        assert app.state.executor.calls == 1
        invokes = [body for path, body in offline.proxy.calls if path == "/invoke"]
        assert len(invokes) == (0 if fault == "token_failure" else 1)
        if invokes:
            tokens = [body for path, body in offline.proxy.calls if path.endswith("/token")]
            assert tokens[0]["plan"]["steps"][0]["params"] == invokes[0]["params"]
            assert set(invokes[0]["params"]) == {
                "incident_id",
                "summary",
                "handoff_note",
                "_dispatch",
            }
        evidence = client.get("/api/policy/evidence").json()
        assert evidence["mode"] == "LIVE" and len(evidence["events"]) == 1
        assert "ak_test_" not in json.dumps(evidence)
    again = offline_live(state)
    with composition(live_settings, enforcement=again.live) as (runtime, store, *_):
        assert runtime.actions.get(action["action_id"]).state.value == state_name
        assert len(store.records()) == effects and not again.proxy.calls


async def test_permit_cannot_be_issued_before_durable_authorized_claim(settings, state):
    offline = offline_live(state)
    with composition(replace(settings, enforcement_mode="real"), enforcement=offline.live) as parts:
        runtime, store, _, live, executor = parts
        _, action, principal = await admitted(runtime, state)
        live.issuer.track(action.action_id)
        denied = await executor.execute(execution_spec(store), action.effect_key, context())
        assert denied.category.value == "CONFIRMED_FAILURE" and not offline.proxy.calls
        action = runtime.gateway.authorize(
            ActionCommand(action.action_id, 1, str(uuid4())), principal
        ).action
        live.issuer.track(action.action_id)
        denied = await executor.execute(execution_spec(store), action.effect_key, context())
        assert denied.category.value == "CONFIRMED_FAILURE" and not store.records()


@pytest.mark.parametrize(
    "field,value",
    [
        ("tool_name", "unregistered"),
        ("target", "wrong"),
        ("execution_scope", str(uuid4())),
        ("adapter_id", "wrong"),
        ("binding_revision", "wrong"),
    ],
)
def test_mapping_closed_identity(state, field, value):
    store = load_store(state)
    with pytest.raises(ValueError):
        captured_step(replace(execution_spec(store), **{field: value}), store.binding, {})


def signed_params(state):
    import base64

    store = load_store(state)
    spec = execution_spec(store)
    issuer = PermitIssuer(state / "armoriq", store)
    now = time.time()
    body = {
        "version": 1,
        "service": "aegis-relay-mcp",
        "action_id": str(uuid4()),
        "run_id": str(uuid4()),
        "authorization_id": str(uuid4()),
        "attempt_id": str(uuid4()),
        "effect_key": str(uuid4()),
        "payload_digest": spec.payload_digest(),
        "binding": vars(store.binding),
        "store_id": store.store_id,
        "issued_at": now,
        "expires_at": now + 4,
    }
    permit = {
        "body": body,
        "signature": base64.b64encode(issuer.key.sign(canonical(body))).decode(),
    }
    return dict(spec.arguments) | {"_dispatch": permit}


def rpc(client, method, params=None, *, headers=None):
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return json.loads(response.text.split("data: ")[1])


def mcp_client(state):
    provision_live(state)
    return TestClient(
        create_mcp_app(state),
        headers={
            "Authorization": "Bearer " + (state / "armoriq" / "mcp.bearer").read_text("ascii")
        },
    )


def test_mcp_protocol_auth_and_one_effect(state):
    client = mcp_client(state)
    init = rpc(client, "initialize", {"protocolVersion": "2024-11-05"})
    assert init["result"]["serverInfo"]["name"] == "aegis-relay-mcp"
    tools = rpc(client, "tools/list")["result"]["tools"]
    assert {t["name"] for t in tools} == {"create_incident_handoff", "purge_incident_history"}
    assert client.post("/mcp", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/mcp", headers={"Origin": "http://127.0.0.1"}).status_code == 403
    assert client.get("/").status_code == 404 and client.get("/api/handoffs").status_code == 404
    params = signed_params(state)
    first = rpc(client, "tools/call", {"name": "create_incident_handoff", "arguments": params})
    second = rpc(client, "tools/call", {"name": "create_incident_handoff", "arguments": params})
    assert first == second and len(load_store(state).records()) == 1
    assert rpc(
        client,
        "tools/call",
        {"name": "purge_incident_history", "arguments": {"probe_id": str(uuid4())}},
    )["result"]["isError"]
    assert len(load_store(state).records()) == 1


@pytest.mark.parametrize(
    "corruption",
    ["missing", "expired", "signature", "payload", "scope", "store", "action", "extra", "service"],
)
def test_mcp_rejects_untrusted_permits_without_effect(state, corruption):
    import base64

    client = mcp_client(state)
    args = signed_params(state)
    if corruption == "missing":
        del args["_dispatch"]
    elif corruption == "payload":
        args["summary"] = "changed after approval"
    elif corruption == "extra":
        args["arbitrary"] = "code"
    else:
        body = args["_dispatch"]["body"]
        if corruption == "signature":
            args["_dispatch"]["signature"] = "A" * 88
        elif corruption == "scope":
            body["binding"]["execution_scope"] = str(uuid4())
        elif corruption == "store":
            body["store_id"] = str(uuid4())
        elif corruption == "action":
            body["action_id"] = "invalid"
        elif corruption == "service":
            body["service"] = "other-mcp"
        else:
            body["issued_at"], body["expires_at"] = time.time() - 10, time.time() - 6
        if corruption != "signature":
            issuer = PermitIssuer(state / "armoriq", load_store(state))
            args["_dispatch"]["signature"] = base64.b64encode(
                issuer.key.sign(canonical(body))
            ).decode()
    result = rpc(client, "tools/call", {"name": "create_incident_handoff", "arguments": args})
    assert "error" in result and not load_store(state).records()


def test_mcp_conflicting_payload_does_not_overwrite(state):
    import base64

    client = mcp_client(state)
    args = signed_params(state)
    assert "result" in rpc(
        client, "tools/call", {"name": "create_incident_handoff", "arguments": args}
    )
    changed = copy.deepcopy(args)
    changed["summary"] = "conflicting reviewed input"
    store = load_store(state)
    spec = replace(
        execution_spec(store), arguments={k: v for k, v in changed.items() if k != "_dispatch"}
    )
    body = changed["_dispatch"]["body"]
    body["payload_digest"] = spec.payload_digest()
    issuer = PermitIssuer(state / "armoriq", store)
    changed["_dispatch"]["signature"] = base64.b64encode(issuer.key.sign(canonical(body))).decode()
    assert "error" in rpc(
        client, "tools/call", {"name": "create_incident_handoff", "arguments": changed}
    )
    assert store.records()[0]["summary"] == args["summary"] and len(store.records()) == 1


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("deny", "ARMORIQ_POLICY_DENIED"),
        ("mismatch", "INTENT_MISMATCH"),
        ("none", "CANARY_REACHED_SERVICE"),
    ],
)
async def test_canary_separately_captured_plan_never_deletes(state, fault, expected):
    offline = offline_live(state, fault=fault)
    try:
        result = await offline.live.canary()
        assert result["status"] == expected and result["effect_store_unchanged"]
        assert result["policy_denial_verified"] == (fault == "deny")
        token, invoke = offline.proxy.calls
        assert token[1]["plan"]["steps"][0]["params"] == invoke[1]["params"]
        assert invoke[1]["action"] == "purge_incident_history"
    finally:
        offline.live.close()


async def test_late_token_never_redispatches_after_core_unknown(settings, state):
    offline = offline_live(state, fault="late_token")
    with composition(replace(settings, enforcement_mode="real"), enforcement=offline.live) as parts:
        runtime, store, _, live, _ = parts
        _, action, principal = await admitted(runtime, state)
        action = runtime.gateway.authorize(
            ActionCommand(action.action_id, 1, str(uuid4())), principal
        ).action
        live.issuer.track(action.action_id)
        result = await runtime.gateway.execute(
            ActionCommand(action.action_id, 2, str(uuid4())), principal
        )
        assert result.action.state.value == "Unknown"
        await asyncio.sleep(0.5)
        assert not store.records() and len(offline.proxy.calls) == 1


async def test_generic_sdk_403_is_not_policy_denial_evidence(state):
    offline = offline_live(state, fault="token_403")
    try:
        result = await offline.live.canary()
        assert result["status"] == "SDK_DENIED_UNCLASSIFIED"
        assert not result["policy_denial_verified"] and result["effect_store_unchanged"]
        assert len(offline.proxy.calls) == 1
    finally:
        offline.live.close()


def test_live_check_requires_explicit_opt_in(monkeypatch):
    from scripts.phase2_live_check import main

    monkeypatch.delenv("SAFEOPS_REAL_E2E", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "phase2_live_check",
            "--state",
            "unused-state",
            "--public-url",
            "https://unused.example/mcp",
            "--output",
            "unused-output",
        ],
    )
    with pytest.raises(RuntimeError, match="Opt in"):
        main()
