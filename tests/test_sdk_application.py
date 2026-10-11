"""SDK-only in the real FastAPI composition, using actual SDK with OFFLINE transport."""

import json
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from safeops.configuration import Settings
from safeops.integration.dispatch_permit import load_store, provision_live
from safeops.integration.sdk_application import MCP_ID, ORG_ID, SDKOnlyApplication
from safeops.main import create_app
from tests.conftest import approved_action, command_headers
from tests.test_sdk_only import POLICY_ID, POLICY_NAME, OfflineSDK


class ApplicationWire(OfflineSDK):
    def handle(self, request):
        path = request.url.path
        if path in {"/iap/sdk/bootstrap", "/iap/sdk/resolve-user"}:
            self.requests.append((path, json.loads(request.content)))
            if path.endswith("bootstrap"):
                return httpx.Response(
                    200,
                    json={
                        "org": {"orgId": ORG_ID},
                        "mcps": [{"mcpId": MCP_ID, "name": "aegis-relay-mcp"}],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "policies": [
                        {
                            "policyId": POLICY_ID,
                            "policyName": POLICY_NAME,
                            "targetId": str(uuid4()) if self.fault == "wrong_target" else MCP_ID,
                            "targetType": "mcp_server",
                            "rules": {"allowedTools": ["create_incident_handoff"]},
                            "defaultEnforcementAction": "block",
                        }
                    ]
                },
            )
        if path == "/iap/audit" or path.endswith("/status"):
            self.requests.append((path, json.loads(request.content)))
            failed = self.fault == "report_error"
            return httpx.Response(
                503 if failed else 200,
                json={
                    "id": str(uuid4()),
                    **(
                        {}
                        if self.fault == "report_without_boolean" and path == "/iap/audit"
                        else {"success": not failed}
                    ),
                    "plan_id": path.split("/")[-2] if path.endswith("/status") else None,
                },
                headers={"x-request-id": str(uuid4())},
            )
        return super().handle(request)


def offline_application(state, *, fault="none"):
    if not (state / "armoriq").exists():
        provision_live(state)
    wire = ApplicationWire(fault)
    application = SDKOnlyApplication(
        state,
        load_store(state),
        client_factory=lambda: (wire.client(), "offline@example.test"),
        offline_test=True,
    )
    return application, wire


def sdk_app(state, fault="none"):
    boundary, wire = offline_application(state, fault=fault)
    app = create_app(
        Settings(
            state=state,
            provider="fixture",
            predecessor_stopped=True,
            enforcement_mode="sdk-only",
        ),
        enforcement=boundary,
    )
    client = TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={
            "Authorization": "Bearer " + (state / "capability").read_text("ascii"),
        },
    )
    return client, boundary, wire


def prepare(client, action, **body):
    return client.post(
        f"/api/actions/{action['action_id']}/sdk-stage",
        json={
            "expected_action_version": action["version"],
            **body,
        },
    )


def execute(client, action, headers=None):
    return client.post(
        f"/api/actions/{action['action_id']}/execute",
        json={
            "expected_action_version": action["version"],
        },
        headers=headers or command_headers(),
    )


def test_real_app_sdk_lifecycle_and_exact_replay(state):
    client, boundary, wire = sdk_app(state)
    with client:
        _, action = approved_action(client)
        assert prepare(client, action).json()["status"] == "READY"
        assert boundary.store.records() == []
        first_paths = [p for p, _ in wire.requests]
        assert prepare(client, action).json()["status"] == "READY"
        assert [p for p, _ in wire.requests] == first_paths  # no extra token
        headers = command_headers()
        result = execute(client, action, headers)
        assert result.status_code == 200, result.text
        assert result.json()["action"]["state"] == "Succeeded"
        stage = client.get(f"/api/actions/{action['action_id']}/sdk-stage").json()
        assert stage["audit"]["status"] == "SDK_AUDIT_POST_ACKNOWLEDGED"
        assert stage["policy"]["transport"] == "OFFLINE_TEST"
        assert stage["policy"]["explicit_allow_confirmed"] is True
        assert stage["policy"]["policy_id"] == POLICY_ID
        assert stage["policy"]["tool"] == "create_incident_handoff"
        assert len(boundary.store.records()) == 1
        paths = list(wire.requests)
        assert execute(client, action, headers).json()["replayed"]
        assert wire.requests == paths
        assert prepare(client, action).status_code == 409


def test_pending_or_unapproved_cannot_stage_or_execute(state):
    client, boundary, wire = sdk_app(state)
    with client:
        run = client.post("/api/runs", json={"text": "INC-24002"}).json()
        assert (
            client.post(
                f"/api/runs/{run['run_id']}/actions",
                json={
                    "expected_run_version": run["version"],
                },
                headers=command_headers(),
            ).status_code
            == 409
        )
        _, action = approved_action(client, authorize=False)
        assert prepare(client, action).status_code == 409
        assert execute(client, action).status_code == 409
        assert wire.requests == [] and boundary.store.records() == []


@pytest.mark.parametrize(
    "change",
    [
        {"expected_action_version": 1},
        {"expected_action_version": True},
        {"arguments": {"incident_id": "INC-23001"}},
        {"intent_token": "forbidden"},
    ],
)
def test_stage_request_cannot_replace_approved_identity(state, change):
    client, boundary, wire = sdk_app(state)
    with client:
        _, action = approved_action(client)
        assert prepare(client, action, **change).status_code == 409
        assert wire.requests == [] and boundary.store.records() == []


def test_missing_stage_preserves_authorized_for_explicit_prepare(state):
    client, boundary, wire = sdk_app(state)
    with client:
        _, action = approved_action(client)
        assert execute(client, action).json()["error"]["code"] == "SDK_STAGE_REQUIRED"
        assert client.get(f"/api/actions/{action['action_id']}").json()["state"] == "Authorized"
        assert wire.requests == [] and boundary.store.records() == []
        assert prepare(client, action).json()["status"] == "READY"


def test_expired_stage_reprepare_is_explicit_and_keeps_same_core_identity(state):
    client, boundary, wire = sdk_app(state)
    with client:
        _, action = approved_action(client)
        prepare(client, action)
        executor = boundary.stages[action["action_id"]]
        token = executor.stage.session.current_token
        executor.stage.session._current_token = token.model_copy(update={"expires_at": 0})
        assert execute(client, action).status_code == 409
        assert len([p for p, _ in wire.requests if p.endswith("/token")]) == 1
        assert prepare(client, action).json()["status"] == "READY"
        assert len([p for p, _ in wire.requests if p.endswith("/token")]) == 2
        assert boundary.store.records() == []


def test_restart_loses_stage_but_authorized_action_can_be_explicitly_prepared(state):
    client, _, wire = sdk_app(state)
    with client:
        _, action = approved_action(client)
        prepare(client, action)
    client, boundary, fresh_wire = sdk_app(state)
    with client:
        assert execute(client, action).status_code == 409
        assert fresh_wire.requests == []
        assert prepare(client, action).json()["status"] == "READY"
        assert execute(client, action).json()["action"]["state"] == "Succeeded"
        assert len(boundary.store.records()) == 1
        assert len([p for p, _ in wire.requests if p.endswith("/token")]) == 1


@pytest.mark.parametrize(
    "fault",
    ["deny", "hold", "timeout", "non200_allow", "wrong_policy", "wrong_target", "token_error"],
)
def test_app_remote_refusal_never_writes(state, fault):
    client, boundary, wire = sdk_app(state, fault)
    with client:
        _, action = approved_action(client)
        stage = prepare(client, action)
        if stage.status_code == 200:
            assert execute(client, action).json()["action"]["state"] == "Failed"
        assert boundary.store.records() == []
        assert not any(p == "/iap/audit" for p, _ in wire.requests)


def test_report_failure_is_separate_from_succeeded_and_never_retried(state):
    client, boundary, wire = sdk_app(state, "report_error")
    with client:
        _, action = approved_action(client)
        prepare(client, action)
        headers = command_headers()
        assert execute(client, action, headers).json()["action"]["state"] == "Succeeded"
        assert (
            client.get(f"/api/actions/{action['action_id']}/sdk-stage").json()["audit"]["status"]
            == "SDK_AUDIT_UNVERIFIED"
        )
        paths = list(wire.requests)
        assert execute(client, action, headers).json()["replayed"]
        assert wire.requests == paths and len(boundary.store.records()) == 1


def test_capability_origin_and_redaction(state):
    client, boundary, wire = sdk_app(state)
    with client:
        _, action = approved_action(client)
        path = f"/api/actions/{action['action_id']}/sdk-stage"
        assert (
            client.post(
                path, json={"expected_action_version": 2}, headers={"Authorization": "Bearer bad"}
            ).status_code
            == 401
        )
        assert (
            client.post(
                path,
                json={"expected_action_version": 2},
                headers={"Origin": "https://evil.invalid"},
            ).status_code
            == 403
        )
        assert wire.requests == []
        prepare(client, action)
        execute(client, action)
        exposed = json.dumps(client.get(path).json()) + json.dumps(client.get("/api/status").json())
        assert "offline@example.test" not in exposed
        assert "intent_token" not in exposed and "raw_token" not in exposed
        assert (state / "capability").read_text("ascii") not in exposed
        assert str(state) not in exposed and "ak_test_offline_only" not in exposed
        assert len(boundary.store.records()) == 1


def test_token_from_other_action_rejected_without_policy_or_write(state):
    client, boundary, wire = sdk_app(state)
    with client:
        _, first = approved_action(client)
        _, second = approved_action(client)
        prepare(client, first)
        prepare(client, second)
        one, two = boundary.stages[first["action_id"]], boundary.stages[second["action_id"]]
        two.stage = replace(two.stage, session=one.stage.session)
        count = len(wire.requests)
        assert execute(client, second).status_code == 409
        assert len(wire.requests) == count and boundary.store.records() == []


def test_unknown_preserved_and_terminal_replay_never_prepares_again(state, monkeypatch):
    client, boundary, wire = sdk_app(state)
    with client:
        _, action = approved_action(client)
        prepare(client, action)
        persist = boundary.store.persist
        monkeypatch.setattr(boundary.store, "persist", lambda *a: persist(*a, lose_ack=True))
        headers = command_headers()
        assert execute(client, action, headers).json()["action"]["state"] == "Unknown"
        paths = list(wire.requests)
        assert prepare(client, action).status_code == 409
        assert execute(client, action, headers).json()["replayed"]
        assert wire.requests == paths and len(boundary.store.records()) == 1


def test_real_alias_and_proxy_selection_are_additive(settings):
    assert replace(settings, enforcement_mode="proxy").enforcement_mode == "proxy"
    assert replace(settings, enforcement_mode="real").enforcement_mode == "real"
    with pytest.raises(ValueError):
        replace(settings, enforcement_mode="sdk-only", executor_fault="policy_deny")


def test_remote_allow_cannot_bypass_forged_permit(state, monkeypatch):
    client, boundary, _ = sdk_app(state)
    with client:
        _, action = approved_action(client)
        prepare(client, action)
        executor = boundary.stages[action["action_id"]]
        issue = executor.issuer.issue

        def forged(*args):
            permit = issue(*args)
            return {**permit, "signature": "invalid"}

        monkeypatch.setattr(executor.issuer, "issue", forged)
        assert execute(client, action).json()["action"]["state"] == "Failed"
        assert executor.evidence["explicit_remote_allow"]
        assert executor.business_calls == 0 and boundary.store.records() == []


def test_audit_storage_failure_never_repeats_success_or_reporting(state, monkeypatch):
    client, boundary, wire = sdk_app(state)
    with client:
        _, action = approved_action(client)
        prepare(client, action)

        def unavailable(*args, **kwargs):
            raise OSError("OFFLINE audit storage unavailable")

        monkeypatch.setattr(boundary.audit, "record", unavailable)
        headers = command_headers()
        assert execute(client, action, headers).json()["action"]["state"] == "Succeeded"
        paths = list(wire.requests)
        assert execute(client, action, headers).json()["replayed"]
        assert paths == wire.requests and len(boundary.store.records()) == 1
        assert (
            client.get(f"/api/actions/{action['action_id']}/sdk-stage").json()["audit_storage"]
            == "UNAVAILABLE"
        )


def test_audit_ack_does_not_invent_a_missing_success_boolean(state):
    client, _, _ = sdk_app(state, "report_without_boolean")
    with client:
        _, action = approved_action(client)
        prepare(client, action)
        assert execute(client, action).json()["action"]["state"] == "Succeeded"
        event = client.get(f"/api/actions/{action['action_id']}/sdk-stage").json()["audit"]
        assert event["status"] == "SDK_AUDIT_POST_ACKNOWLEDGED"
        report = next(e for e in event["diagnostics"]["http_events"] if e["phase"] == "REPORT")
        assert report["success"] is None
