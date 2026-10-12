import pytest
from fastapi.testclient import TestClient

from safeops.main import create_app
from tests.conftest import approved_action, command_headers, fault_settings


def test_health_status_security(client, state):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health").json()["product"] == "Aegis Relay"
    metadata = client.app.openapi()["info"]
    assert metadata["title"] == "Aegis Relay"
    assert metadata["description"] == "A permissioned AI agent for secure incident handoffs."
    assert client.get("/api/status").json()["provider"]["mode"] == "fixture"
    html = client.get("/")
    assert "<title>Aegis Relay — Agent Execution Console</title>" in html.text
    assert "<h1>Agent Execution Console</h1>" in html.text
    assert "Trust the intent. Govern the action." in html.text
    assert "permissioned AI agent execution console for governed incident handoffs." in html.text
    assert "LOCAL / MOCK" in html.text
    assert (state / "capability").read_text("ascii") not in html.text
    assert "frame-ancestors 'none'" in html.headers["content-security-policy"]
    assert client.get("/api/handoffs", headers={"Authorization": "Bearer bad"}).status_code == 401
    assert (
        client.post(
            "/api/runs", json={"text": "INC-1042"}, headers={"Origin": "https://evil.invalid"}
        ).status_code
        == 403
    )
    assert client.get("/api/handoffs?capability=forbidden").status_code == 400
    assert client.get("/", headers={"Host": "evil.invalid"}).status_code == 400


def test_plan_preview_and_rejection(client):
    result = client.post("/api/plans", json={"text": "Create handoff for INC-1042"})
    assert result.status_code == 200 and result.json()["state"] == "PlanValidated"
    run = client.post("/api/runs", json={"text": "Create handoff for INC-1042"}).json()
    response = client.post(
        f"/api/runs/{run['run_id']}/approval", json={"decision": "REJECT", "expected_version": 4}
    )
    assert response.json()["state"] == "Rejected"
    response = client.post(
        f"/api/runs/{run['run_id']}/actions",
        json={"expected_run_version": 5},
        headers=command_headers(),
    )
    assert response.status_code == 409
    assert client.get("/api/handoffs").json()["records"] == []


def test_happy_path_exact_replay_and_key_conflict(client):
    _, action = approved_action(client)
    path = f"/api/actions/{action['action_id']}/execute"
    headers, body = command_headers(), {"expected_action_version": action["version"]}
    first = client.post(path, json=body, headers=headers)
    assert first.status_code == 200 and first.json()["action"]["state"] == "Succeeded"
    replay = client.post(path, json=body, headers=headers).json()
    assert replay["replayed"] and replay["action"] == first.json()["action"]
    records = client.get("/api/handoffs").json()["records"]
    assert len(records) == 1
    assert records[0]["receipt_reference"] == replay["action"]["result"]["receipt_reference"]
    conflict = client.post(path, json={"expected_action_version": 3}, headers=headers)
    assert (
        conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    )
    assert client.get("/api/handoffs").json()["records"] == records


def test_missing_authorization_stale_approval(client):
    run, action = approved_action(client, authorize=False)
    result = client.post(
        f"/api/actions/{action['action_id']}/execute",
        json={"expected_action_version": 1},
        headers=command_headers(),
    )
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "ACTION_NOT_EXECUTABLE"
    stale = client.post(
        f"/api/runs/{run['run_id']}/approval", json={"decision": "APPROVE", "expected_version": 4}
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "STALE_RUN_VERSION"
    assert client.get("/api/handoffs").json()["records"] == []


def test_missing_key_and_invalid_contract(client):
    _, action = approved_action(client)
    path = f"/api/actions/{action['action_id']}/execute"
    assert client.post(path, json={"expected_action_version": 2}).status_code == 428
    assert (
        client.post(
            path, json={"expected_action_version": True}, headers=command_headers()
        ).status_code
        == 400
    )
    assert client.post("/api/runs", json={"text": "INC-1", "extra": True}).status_code == 400
    assert client.get("/api/handoffs").json()["records"] == []


def test_no_implicit_approval_and_no_plan_substitution(client):
    run = client.post("/api/runs", json={"text": "Create handoff for INC-1042"}).json()
    admission = client.post(
        f"/api/runs/{run['run_id']}/actions",
        json={"expected_run_version": run["version"]},
        headers=command_headers(),
    )
    assert admission.status_code == 409
    replacement = client.post(
        f"/api/runs/{run['run_id']}/approval",
        json={"decision": "APPROVE", "expected_version": 4, "plan": {"target": "wrong"}},
    )
    assert replacement.status_code == 400
    assert replacement.json()["error"]["code"] == "INVALID_APPROVAL"
    assert client.get(f"/api/runs/{run['run_id']}").json() == run
    assert client.get("/api/handoffs").json()["records"] == []


def test_mock_policy_denial_is_not_core_action(client):
    result = client.post("/api/policy/test", json={"operation": "purge_incident_history"})
    assert result.status_code == 403
    data = result.json()
    assert data["mode"] == "MOCK" and data["status"] == "PolicyDenied"
    assert not data["core_action_created"] and not data["business_effect_executed"]
    assert client.get("/api/handoffs").json()["records"] == []
    assert client.get("/api/policy/evidence").json()["events"][0]["status"] == "PolicyDenied"


@pytest.mark.parametrize(
    "fault,code",
    [
        ("timeout", "MODEL_TIMEOUT"),
        ("invalid_json", "PLAN_VALIDATION_ERROR"),
        ("unavailable", "INTERNAL_ERROR"),
    ],
)
def test_provider_failure_persisted(settings, state, fault, code):
    app = create_app(fault_settings(settings, fixture_fault=fault))
    with TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={"Authorization": "Bearer " + (state / "capability").read_text("ascii")},
    ) as client:
        run = client.post("/api/runs", json={"text": "INC-1042"}).json()
        assert run["state"] == "PlanRejected" and run["error"]["code"] == code
        assert client.get(f"/api/runs/{run['run_id']}").json() == run
        assert client.get("/api/handoffs").json()["records"] == []
        assert client.get(f"/api/runs/{run['run_id']}/actions").json()["actions"] == []


def test_mock_denial_inside_real_execution(settings, state):
    app = create_app(fault_settings(settings, executor_fault="policy_deny"))
    with TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={"Authorization": "Bearer " + (state / "capability").read_text("ascii")},
    ) as client:
        _, action = approved_action(client)
        response = client.post(
            f"/api/actions/{action['action_id']}/execute",
            json={"expected_action_version": 2},
            headers=command_headers(),
        )
        assert response.json()["action"]["state"] == "Failed"
        assert response.json()["action"]["result"].get("receipt_reference") is None
        assert client.get("/api/handoffs").json()["records"] == []
        assert client.get("/api/policy/evidence").json()["events"][0]["status"] == "PolicyDenied"
