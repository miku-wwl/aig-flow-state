from uuid import UUID

from agentic_intent_gate.runtime import EXTERNAL_PAYLOAD_REVISION, Outcome, ToolOutcome

from safeops.domain.handoff import valid_arguments
from safeops.execution.handoff_store import StoreConflict, StoreIdentityMismatch
from safeops.integration.armoriq_boundary import EnforcementStatus


class HandoffExecutor:
    def __init__(self, store, enforcement, *, lose_ack=False):
        self.store, self.enforcement, self.lose_ack = store, enforcement, lose_ack
        self.calls = 0

    async def execute(self, spec, effect_key, context):
        self.calls += 1

        def evidence(category, *, receipt=None, reason=None):
            return ToolOutcome(
                category,
                effect_key,
                spec.execution_scope,
                spec.target,
                spec.payload_digest(),
                receipt,
                reason,
            )

        try:
            if (
                not self.store.binding.matches(spec)
                or spec.identity_revision != EXTERNAL_PAYLOAD_REVISION
                or not valid_arguments(dict(spec.arguments))
                or str(UUID(effect_key, version=4)) != effect_key
                or str(UUID(context.attempt_id, version=4)) != context.attempt_id
            ):
                return evidence(Outcome.CONFIRMED_FAILURE, reason="INPUT_REJECTED")
            if context.expired():
                return ToolOutcome(Outcome.UNKNOWN_OUTCOME)
            decision = await self.enforcement.check(
                spec, approved_payload_digest=spec.payload_digest()
            )
            self.store.record_policy(spec.tool_name, decision, effect_key=effect_key)
            if decision.status in {EnforcementStatus.DENIED, EnforcementStatus.MISMATCH}:
                # Core accepts only three no-effect reasons; policy evidence retains detail.
                return evidence(Outcome.CONFIRMED_FAILURE, reason="INPUT_REJECTED")
            if decision.status != EnforcementStatus.ALLOWED:
                return ToolOutcome(Outcome.UNKNOWN_OUTCOME)
            receipt = self.store.persist(spec, effect_key, context, lose_ack=self.lose_ack)
            return evidence(Outcome.SUCCESS, receipt=receipt)
        except StoreConflict:
            return evidence(Outcome.CONFIRMED_FAILURE, reason="PAYLOAD_CONFLICT")
        except StoreIdentityMismatch:
            return evidence(Outcome.CONFIRMED_FAILURE, reason="STORE_IDENTITY_MISMATCH")
        except Exception:
            return ToolOutcome(Outcome.UNKNOWN_OUTCOME)
