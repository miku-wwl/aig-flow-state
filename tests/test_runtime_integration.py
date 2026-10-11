import asyncio
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from agentic_intent_gate.runtime import (
    ActionCommand,
    AdmissionCommand,
    ApprovalChoice,
    ApprovalDecisionRequest,
    Intent,
)

from safeops.integration.mock_armoriq import MockArmorIQClient
from safeops.integration.runtime_composition import composition


def principal_for(runtime, state):
    return runtime.verifier.verify("Bearer " + (state / "capability").read_text("ascii"))


async def admitted(runtime, state):
    principal = principal_for(runtime, state)
    run = await runtime.run_service.create(Intent("Create handoff for INC-1042"))
    run = runtime.run_service.decide(
        run.run_id, ApprovalDecisionRequest(ApprovalChoice.APPROVE, run.version)
    )
    action = runtime.gateway.admit(
        AdmissionCommand(run.run_id, run.version, principal.subject_id, str(uuid4())), principal
    ).action
    return run, action, principal


async def test_exact_binding_and_independent_authorization(settings, state):
    with composition(settings) as (runtime, store, _, _, executor):
        run, action, principal = await admitted(runtime, state)
        assert runtime.run_service.get(run.run_id).to_dict() == run.to_dict()
        assert action.state.value == "Pending" and action.authorization is None
        with pytest.raises(Exception) as error:  # noqa: B017
            await runtime.gateway.execute(
                ActionCommand(action.action_id, 1, str(uuid4())), principal
            )
        assert error.value.code.value == "ACTION_NOT_EXECUTABLE"
        assert store.records() == [] and executor.calls == 0
        forged = replace(principal, execution_scope=str(uuid4()))
        with pytest.raises(Exception) as error:  # noqa: B017
            runtime.gateway.authorize(ActionCommand(action.action_id, 1, str(uuid4())), forged)
        assert error.value.code.value == "ACTION_NOT_AUTHORIZED"
        assert store.records() == []


async def test_concurrent_claims_dispatch_once(settings, state):
    with composition(settings) as (runtime, store, _, _, executor):
        base = MockArmorIQClient(store.binding)
        entered, release = asyncio.Event(), asyncio.Event()

        class HeldBoundary:
            async def check(self, spec, *, approved_payload_digest):
                entered.set()
                await release.wait()
                return await base.check(spec, approved_payload_digest=approved_payload_digest)

        executor.enforcement = HeldBoundary()
        _, action, principal = await admitted(runtime, state)
        action = runtime.gateway.authorize(
            ActionCommand(action.action_id, 1, str(uuid4())), principal
        ).action
        command = ActionCommand(action.action_id, action.version, str(uuid4()))
        first = asyncio.create_task(runtime.gateway.execute(command, principal))
        await entered.wait()
        concurrent = await runtime.gateway.execute(command, principal)
        assert concurrent.replayed and concurrent.action.state.value == "Executing"
        with pytest.raises(Exception) as error:  # noqa: B017
            await runtime.gateway.execute(
                ActionCommand(action.action_id, concurrent.action.version, str(uuid4())), principal
            )
        assert error.value.code.value == "EXECUTION_ALREADY_STARTED"
        release.set()
        result = await first
        assert result.action.state.value == "Succeeded"
        assert executor.calls == 1 and len(store.records()) == 1


def test_startup_fails_closed_for_missing_gate_and_changed_identity(settings, state):
    manifest = state / "identity.json"
    original = json.loads(manifest.read_text("utf-8"))
    changed = original | {"binding": original["binding"] | {"adapter_id": "wrong"}}
    manifest.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="binding mismatch"), composition(settings):
        pass
    manifest.write_text(json.dumps(original), encoding="utf-8")
    # Renaming a fixture DB proves startup cannot silently create a replacement.
    (state / "gate.sqlite3").rename(state / "gate-preserved.sqlite3")
    with pytest.raises(ValueError, match="Missing gate DB"), composition(settings):
        pass
    assert not (state / "gate.sqlite3").exists()
