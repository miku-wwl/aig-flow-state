import hashlib
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from agentic_intent_gate.runtime import ActionCommand
from fastapi.testclient import TestClient

from safeops.integration.runtime_composition import composition, provision
from safeops.main import create_app
from tests.conftest import approved_action, command_headers
from tests.test_runtime_integration import admitted, principal_for


def identity_hashes(state):
    return {
        name: hashlib.sha256((state / name).read_bytes()).hexdigest()
        for name in ("identity.json", "capability")
    }


def test_reprovision_refuses_existing_state(state):
    before = identity_hashes(state)
    with pytest.raises(FileExistsError):
        provision(state)
    assert identity_hashes(state) == before


def test_graceful_restart_preserves_receipt(settings, state):
    before = identity_hashes(state)
    headers = {"Authorization": "Bearer " + (state / "capability").read_text("ascii")}
    with TestClient(create_app(settings), base_url="http://127.0.0.1", headers=headers) as client:
        run, action = approved_action(client)
        result = client.post(
            f"/api/actions/{action['action_id']}/execute",
            json={"expected_action_version": 2},
            headers=command_headers(),
        ).json()["action"]
        records = client.get("/api/handoffs").json()["records"]
    with TestClient(create_app(settings), base_url="http://127.0.0.1", headers=headers) as client:
        assert client.get(f"/api/runs/{run['run_id']}").json() == run
        assert client.get(f"/api/actions/{action['action_id']}").json() == result
        assert client.get("/api/handoffs").json()["records"] == records
        assert client.app.state.executor.calls == 0
    assert identity_hashes(state) == before


async def test_unknown_after_commit_never_redispatches(settings, state):
    faulty = replace(settings, executor_fault="post_commit_ack_loss")
    with composition(faulty) as (runtime, store, _, _, executor):
        _, action, principal = await admitted(runtime, state)
        action = runtime.gateway.authorize(
            ActionCommand(action.action_id, 1, str(uuid4())), principal
        ).action
        command = ActionCommand(action.action_id, 2, str(uuid4()))
        result = await runtime.gateway.execute(command, principal)
        assert result.action.state.value == "Unknown" and len(store.records()) == 1
        assert result.action.result["receipt_reference"] is None
        replay = await runtime.gateway.execute(command, principal)
        assert replay.replayed and replay.action == result.action and executor.calls == 1
        record = store.records()[0]
    with composition(settings) as (runtime, store, _, _, executor):
        principal = principal_for(runtime, state)
        assert runtime.gateway.get(action.action_id, principal).state.value == "Unknown"
        with pytest.raises(Exception) as error:  # noqa: B017
            await runtime.gateway.execute(
                ActionCommand(action.action_id, 4, str(uuid4())), principal
            )
        assert error.value.code.value in {"EXECUTION_ALREADY_STARTED", "STALE_ACTION_VERSION"}
        assert store.records() == [record] and executor.calls == 0


async def test_interrupted_claim_recovers_unknown_without_effect(settings, state):
    with composition(settings) as (runtime, store, _, _, _):
        _, action, principal = await admitted(runtime, state)
        runtime.gateway.authorize(ActionCommand(action.action_id, 1, str(uuid4())), principal)
        claim = runtime.actions.claim(
            ActionCommand(action.action_id, 2, str(uuid4())), principal, runtime.gateway.policy
        )
        assert claim.action.state.value == "Executing" and store.records() == []
    with composition(settings) as (runtime, store, _, _, executor):
        assert (
            runtime.gateway.get(action.action_id, principal_for(runtime, state)).state.value
            == "Unknown"
        )
        assert executor.calls == 0 and store.records() == []


def test_owner_lock_and_explicit_predecessor_assertion(settings):
    with composition(settings):
        with pytest.raises(Exception) as error:  # noqa: B017
            with composition(settings):
                pass
        assert error.value.code.value == "DATABASE_UNAVAILABLE"
    with pytest.raises(Exception) as error:  # noqa: B017
        with composition(replace(settings, predecessor_stopped=False)):
            pass
    assert error.value.code.value == "ACTION_NOT_AUTHORIZED"


def test_unsupported_business_schema_not_migrated(settings, state):
    import sqlite3

    with sqlite3.connect(state / "effects.sqlite3") as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(Exception) as error:  # noqa: B017
        with composition(settings):
            pass
    assert type(error.value).__name__ == "StoreIdentityMismatch"
    assert json.loads((state / "identity.json").read_text())["manifest_version"] == 1
