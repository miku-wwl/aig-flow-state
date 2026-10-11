from dataclasses import replace

import pytest
from agentic_intent_gate.runtime import Outcome

from safeops.integration.armoriq_boundary import EnforcementStatus
from safeops.integration.mock_armoriq import MockArmorIQClient
from safeops.integration.runtime_composition import composition
from tests.test_handoff_executor import context, execution_spec


async def test_allow_deny_mismatch(settings):
    with composition(settings) as (_, store, _, boundary, _):
        spec = execution_spec(store)
        allow = await boundary.check(spec, approved_payload_digest=spec.payload_digest())
        assert allow.status == EnforcementStatus.ALLOWED
        deny = await boundary.check(
            replace(spec, tool_name="purge_incident_history"),
            approved_payload_digest=spec.payload_digest(),
        )
        assert deny.status == EnforcementStatus.DENIED
        mismatch = await boundary.check(spec, approved_payload_digest="wrong")
        assert mismatch.status == EnforcementStatus.MISMATCH
        assert store.records() == []


@pytest.mark.parametrize(
    "fault", [EnforcementStatus.UNAVAILABLE, EnforcementStatus.TIMEOUT, EnforcementStatus.AMBIGUOUS]
)
async def test_distinct_boundary_failures(settings, fault):
    with composition(settings) as (_, store, _, _, _):
        boundary = MockArmorIQClient(store.binding, fault=fault)
        result = await boundary.check(execution_spec(store), approved_payload_digest="unused")
        assert result.status == fault and store.records() == []


@pytest.mark.parametrize(
    "fault", [EnforcementStatus.UNAVAILABLE, EnforcementStatus.TIMEOUT, EnforcementStatus.AMBIGUOUS]
)
async def test_boundary_failure_never_creates_business_effect(settings, fault):
    from uuid import uuid4

    with composition(settings) as (_, store, _, _, executor):
        executor.enforcement = MockArmorIQClient(store.binding, fault=fault)
        outcome = await executor.execute(execution_spec(store), str(uuid4()), context())
        assert outcome.category == Outcome.UNKNOWN_OUTCOME
        assert store.records() == []
