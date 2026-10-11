from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from agentic_intent_gate.runtime import ExecutionSpec


class EnforcementStatus(StrEnum):
    ALLOWED = "Allowed"
    DENIED = "PolicyDenied"
    MISMATCH = "IntentParameterMismatch"
    UNAVAILABLE = "ServiceUnavailable"
    TIMEOUT = "Timeout"
    AMBIGUOUS = "AmbiguousInvocationOutcome"


@dataclass(frozen=True)
class EnforcementDecision:
    status: EnforcementStatus
    reason: str


class EnforcementClient(Protocol):
    """Consumer boundary, NOT a claim about ArmorIQ SDK method signatures.

    Phase 2 must review whether enforce-only or proxy invocation is appropriate.
    No ambiguous remote result may be converted into a local success or retry.
    """

    async def check(
        self, spec: ExecutionSpec, *, approved_payload_digest: str
    ) -> EnforcementDecision: ...
