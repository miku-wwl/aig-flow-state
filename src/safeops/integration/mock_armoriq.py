from agentic_intent_gate.runtime import EXTERNAL_PAYLOAD_REVISION

from safeops.integration.armoriq_boundary import EnforcementDecision, EnforcementStatus


class MockArmorIQClient:
    """Explicit local allow/deny fixture. No sponsor network calls or SDK impersonation."""

    def __init__(self, binding, *, allowed_tools=None, fault=None):
        self.binding = binding
        self.allowed_tools = frozenset(
            {"create_incident_handoff"} if allowed_tools is None else allowed_tools
        )
        self.denied_tools = frozenset({"purge_incident_history"})
        self.fault = fault
        self.calls = 0

    async def check(self, spec, *, approved_payload_digest):
        self.calls += 1
        if self.fault is not None:
            return EnforcementDecision(self.fault, "Explicit deterministic boundary fault")
        if spec.tool_name in self.denied_tools or spec.tool_name not in self.allowed_tools:
            return EnforcementDecision(
                EnforcementStatus.DENIED, "Operation denied by offline policy"
            )
        if (
            not self.binding.matches(spec)
            or spec.identity_revision != EXTERNAL_PAYLOAD_REVISION
            or approved_payload_digest != spec.payload_digest()
        ):
            return EnforcementDecision(
                EnforcementStatus.MISMATCH, "Trusted identity or intent mismatch"
            )
        return EnforcementDecision(
            EnforcementStatus.ALLOWED, "Trusted local handoff policy matched"
        )
