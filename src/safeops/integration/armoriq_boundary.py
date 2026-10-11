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
    """Mock check-only boundary; the real adapter separately owns proxy forwarding.

    No ambiguous remote result may become local success or an automatic retry.
    """

    async def check(
        self, spec: ExecutionSpec, *, approved_payload_digest: str
    ) -> EnforcementDecision: ...
