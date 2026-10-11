from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from safeops.configuration import Settings
from safeops.integration.runtime_composition import provision
from safeops.main import create_app


def pytest_configure(config):
    Path(".artifacts").mkdir(exist_ok=True)


@pytest.fixture
def state(tmp_path):
    directory = tmp_path / "state"
    provision(directory)
    return directory


@pytest.fixture
def settings(state):
    return Settings(state=state, provider="fixture", predecessor_stopped=True)


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app, state):
    headers = {"Authorization": "Bearer " + (state / "capability").read_text("ascii")}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        yield client


def command_headers(key=None):
    return {"Idempotency-Key": key or str(uuid4())}


def approved_action(client, *, authorize=True):
    response = client.post("/api/runs", json={"text": "Create handoff for INC-1042"})
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["state"] == "AwaitingApproval"
    run = client.post(
        f"/api/runs/{run['run_id']}/approval",
        json={"decision": "APPROVE", "expected_version": run["version"]},
    ).json()
    response = client.post(
        f"/api/runs/{run['run_id']}/actions",
        json={"expected_run_version": run["version"]},
        headers=command_headers(),
    )
    assert response.status_code == 201, response.text
    action = response.json()["actions"][0]
    if authorize:
        response = client.post(
            f"/api/actions/{action['action_id']}/authorize",
            json={"expected_action_version": action["version"]},
            headers=command_headers(),
        )
        assert response.status_code == 200, response.text
        action = response.json()["action"]
    return run, action


def fault_settings(settings, **kwargs):
    return replace(settings, **kwargs)
