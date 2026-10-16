import json
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from safeops.public_demo import COOKIE, create_public_app, provision_public

ORIGIN = "https://demo.example.com"


@pytest.fixture
def root(tmp_path):
    directory = tmp_path / "public-demo"
    provision_public(directory)
    return directory


@pytest.fixture
def public(root):
    with TestClient(create_public_app(root, ORIGIN, provider="fixture"), base_url=ORIGIN) as client:
        yield client


def start(client):
    response = client.post(
        "/api/demo/session", json={}, headers={"Origin": ORIGIN, "X-Aegis-Demo": "1"}
    )
    assert response.status_code == 200, response.text
    client.headers.update({"Origin": ORIGIN, "X-Aegis-CSRF": response.json()["demo_csrf"]})
    return response


def generate(client):
    response = client.post("/api/runs", json={"text": "Synthetic checkout exercise INC-1042"})
    assert response.status_code == 201, response.text
    assert response.json()["state"] == "AwaitingApproval"
    return response.json()


def approved_action(client):
    run = generate(client)
    approved = client.post(
        f"/api/runs/{run['run_id']}/approval",
        json={"decision": "APPROVE", "expected_version": run["version"]},
    ).json()
    admitted = client.post(
        f"/api/runs/{run['run_id']}/actions",
        json={"expected_run_version": approved["version"]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert admitted.status_code == 201, admitted.text
    return run, admitted.json()["actions"][0]


def execute(client, action):
    authorized = client.post(
        f"/api/actions/{action['action_id']}/authorize",
        json={"expected_action_version": action["version"]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert authorized.status_code == 200, authorized.text
    action = authorized.json()["action"]
    key = str(uuid4())
    body = {"expected_action_version": action["version"]}
    result = client.post(
        f"/api/actions/{action['action_id']}/execute", json=body, headers={"Idempotency-Key": key}
    )
    assert result.status_code == 200, result.text
    return result.json(), body, key


def test_isolated_gates_receipt_and_restart(root):
    app = create_public_app(root, ORIGIN, provider="fixture")
    with TestClient(app, base_url=ORIGIN) as client:
        response = start(client)
        cookie = response.headers["set-cookie"]
        assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
        assert client.get("/api/status").json()["enforcement"] == "MOCK"
        run, action = approved_action(client)
        assert action["state"] == "Pending"
        assert client.get("/api/handoffs").json()["records"] == []
        unauthorized = client.post(
            f"/api/actions/{action['action_id']}/execute",
            json={"expected_action_version": action["version"]},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert unauthorized.status_code == 409
        result, body, key = execute(client, action)
        assert result["action"]["state"] == "Succeeded"
        records = client.get("/api/handoffs").json()["records"]
        assert len(records) == 1
        assert result["action"]["result"]["receipt_reference"] == records[0]["receipt_reference"]
        replay = client.post(
            f"/api/actions/{action['action_id']}/execute",
            json=body,
            headers={"Idempotency-Key": key},
        )
        assert replay.json()["action"] == result["action"]
        cookies = dict(client.cookies)
    # A new gateway process context reuses the same state, never reprovisions it.
    with TestClient(create_public_app(root, ORIGIN, provider="fixture"), base_url=ORIGIN) as client:
        client.cookies.update(cookies)
        status = client.get("/api/status").json()
        assert status["demo_csrf"]
        assert client.get(f"/api/runs/{run['run_id']}").json()["state"] == "Approved"
        assert client.get(f"/api/actions/{action['action_id']}").json()["state"] == "Succeeded"
        assert client.get("/api/handoffs").json()["records"] == records
    with pytest.raises(FileExistsError):
        provision_public(root)


def test_sessions_cannot_read_or_operate_each_other(public):
    start(public)
    run = generate(public)
    old_cookie = public.cookies.get(COOKIE)
    public.cookies.clear()
    start(public)
    assert public.cookies.get(COOKIE) != old_cookie
    assert public.get(f"/api/runs/{run['run_id']}").status_code == 404
    assert public.get("/api/handoffs").json()["records"] == []
    assert public.post(
        f"/api/runs/{run['run_id']}/approval",
        json={"decision": "APPROVE", "expected_version": run["version"]},
    ).status_code in {403, 404}


def test_public_boundary_rejects_privileged_and_cross_origin_requests(public):
    assert public.get("/api/handoffs").status_code == 401
    assert public.post("/api/demo/session", json={}).status_code == 403
    start(public)
    assert public.get("/api/status", headers={"Host": "evil.invalid"}).status_code == 400
    assert public.get("/api/status?token=bad").status_code == 403
    assert (
        public.get("/api/handoffs", headers={"Authorization": "Bearer private"}).status_code == 403
    )
    assert (
        public.post(
            "/api/runs", json={"text": "INC-1"}, headers={"Origin": "https://evil.invalid"}
        ).status_code
        == 403
    )
    assert (
        public.post(
            "/api/runs", json={"text": "INC-1"}, headers={"X-Aegis-CSRF": "bad"}
        ).status_code
        == 403
    )
    action_id = str(uuid4())
    for method, path in [
        ("GET", "/api/admin"),
        ("POST", f"/api/actions/{action_id}/sdk-stage"),
        ("DELETE", "/api/runs"),
    ]:
        assert public.request(method, path).status_code == 403
    assert public.post("/api/runs", content=b"x" * 8193).status_code == 413
    assert public.post("/api/runs", json={"text": "x" * 1501}).status_code == 400
    assert public.post("/api/runs", json={"text": "No incident identifier"}).status_code == 400
    assert public.get("/api/status").json()["provider"]["calls"] == 0


def test_plan_quota_persists_restart(root):
    with TestClient(create_public_app(root, ORIGIN, provider="fixture"), base_url=ORIGIN) as client:
        start(client)
        for _ in range(4):
            generate(client)
        denied = client.post("/api/runs", json={"text": "Synthetic INC-1042"})
        assert denied.status_code == 429
        assert denied.json()["error"]["code"] == "DEMO_PLAN_LIMIT"
        cookies, headers = dict(client.cookies), dict(client.headers)
    with TestClient(create_public_app(root, ORIGIN, provider="fixture"), base_url=ORIGIN) as client:
        client.cookies.update(cookies)
        client.headers.update(headers)
        assert client.post("/api/runs", json={"text": "Synthetic INC-1042"}).status_code == 429


def test_unknown_is_not_redispatched(public, monkeypatch):
    import safeops.public_demo as module

    original = module.create_app
    monkeypatch.setattr(
        module,
        "create_app",
        lambda settings, **kw: original(
            replace(settings, executor_fault="post_commit_ack_loss"), **kw
        ),
    )
    start(public)
    _, action = approved_action(public)
    result, body, key = execute(public, action)
    assert result["action"]["state"] == "Unknown"
    for replay_key in [key, str(uuid4())]:
        public.post(
            f"/api/actions/{action['action_id']}/execute",
            json=body,
            headers={"Idempotency-Key": replay_key},
        )
    assert len(public.get("/api/handoffs").json()["records"]) == 1


def test_no_private_capability_or_state_in_public_content(public, root):
    start(public)
    html = public.get("/").text
    status = public.get("/api/status").json()
    assert status["public_demo"] is True and status["execution_path"] == "mock"
    for path in (root / "sessions").iterdir():
        token = (path / "capability").read_text("ascii")
        assert token not in html and token not in json.dumps(status)
    evidence = public.get("/api/demo/evidence").json()
    assert evidence["historical"] is True and evidence["current_execution"] == "SIMULATION"
    assert public.get("/.runtime/identity.json").status_code == 404
    assert "frame-ancestors 'none'" in public.get("/").headers["content-security-policy"]
