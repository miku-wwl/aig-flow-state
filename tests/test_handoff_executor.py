import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest
from agentic_intent_gate.runtime import (
    EXTERNAL_PAYLOAD_REVISION,
    AttemptContext,
    ExecutionSpec,
    Outcome,
)

from safeops.execution.handoff_store import StoreIdentityMismatch
from safeops.integration.runtime_composition import composition
from safeops.planning.fixture_provider import fixture_plan


def context():
    return AttemptContext(str(uuid4()), asyncio.get_running_loop().time() + 5, asyncio.Event())


def execution_spec(store):
    b = store.binding
    return ExecutionSpec(
        b.tool_name,
        b.tool_version,
        b.target,
        fixture_plan("INC-1042")["steps"][0]["arguments"],
        b.adapter_id,
        b.binding_revision,
        b.execution_scope,
        EXTERNAL_PAYLOAD_REVISION,
    )


async def test_store_exact_replay_payload_conflict(settings):
    with composition(settings) as (_, store, _, _, executor):
        spec, key = execution_spec(store), str(uuid4())
        first = await executor.execute(spec, key, context())
        second = await executor.execute(spec, key, context())
        assert (
            first.category == Outcome.SUCCESS
            and second.receipt_reference == first.receipt_reference
        )
        changed = replace(spec, arguments=dict(spec.arguments) | {"summary": "Different input"})
        conflict = await executor.execute(changed, key, context())
        assert (
            conflict.category == Outcome.CONFIRMED_FAILURE
            and conflict.no_effect_reason == "PAYLOAD_CONFLICT"
        )
        assert (
            len(store.records()) == 1 and store.records()[0]["summary"] == spec.arguments["summary"]
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("target", "wrong"),
        ("adapter_id", "wrong"),
        ("binding_revision", "wrong"),
        ("tool_version", "2"),
        ("execution_scope", str(uuid4())),
    ],
)
async def test_executor_rejects_wrong_trusted_identity(settings, field, value):
    with composition(settings) as (_, store, _, boundary, executor):
        result = await executor.execute(
            replace(execution_spec(store), **{field: value}), str(uuid4()), context()
        )
        assert result.category == Outcome.CONFIRMED_FAILURE
        assert store.records() == [] and boundary.calls == 0


async def test_business_store_concurrent_replay(settings):
    with composition(settings) as (_, store, _, _, _):
        spec, key, attempt = execution_spec(store), str(uuid4()), context()

        # Store is invoked concurrently below; the immutable context deadline is loop-owned.
        class StableContext:
            def expired(self):
                return False

        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(lambda _: store.persist(spec, key, StableContext()), range(4)))
        assert len(set(receipts)) == 1 and len(store.records()) == 1
        assert not attempt.expired()


async def test_mismatched_store_identity_rejected(settings, state):
    with composition(settings) as (_, store, _, _, executor):
        with sqlite3.connect(state / "effects.sqlite3") as db:
            db.execute("UPDATE identity SET store_id='wrong'")
        result = await executor.execute(execution_spec(store), str(uuid4()), context())
        assert result.category == Outcome.CONFIRMED_FAILURE
        assert result.no_effect_reason == "STORE_IDENTITY_MISMATCH"


async def test_business_store_itself_rejects_mismatched_scope(settings):
    with composition(settings) as (_, store, _, _, _):
        wrong_scope = replace(execution_spec(store), execution_scope=str(uuid4()))
        with pytest.raises(StoreIdentityMismatch):
            store.persist(wrong_scope, str(uuid4()), context())
        assert store.records() == []
