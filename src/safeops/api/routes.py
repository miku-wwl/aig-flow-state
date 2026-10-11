from typing import Literal

from agentic_intent_gate.runtime import EXTERNAL_PAYLOAD_REVISION, ExecutionSpec
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from safeops.integration.armoriq_boundary import EnforcementStatus
from safeops.planning.fixture_provider import fixture_plan


class PolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["purge_incident_history", "create_incident_handoff"]


class PolicyResponse(BaseModel):
    mode: Literal["MOCK", "LIVE"] = "MOCK"
    operation: str
    status: str
    reason: str
    core_action_created: bool = False
    business_effect_executed: bool = False


def consumer_routes(app):
    router = APIRouter()

    @router.get("/api/health")
    def health():
        return {
            "status": "ok",
            "product": "Aegis Relay",
            "phase": 2 if getattr(app.state.enforcement, "mode", "MOCK") == "LIVE" else 1,
        }

    @router.get("/api/status")
    def status():
        live = getattr(app.state.enforcement, "mode", "MOCK") == "LIVE"
        live_status = app.state.enforcement.status() if live else None
        label = (
            "Offline SDK test transport — no real platform enforcement"
            if live and live_status["transport"] == "OFFLINE_TEST"
            else "Real ArmorIQ proxy execution — qualification pending"
            if live
            else "Simulated policy enforcement — Phase 1 offline mode"
        )
        return {
            "provider": app.state.provider.status(),
            "enforcement": "LIVE" if live else "MOCK",
            "enforcement_label": label,
            "armoriq": {key: value for key, value in live_status.items() if key != "last_event"}
            if live
            else None,
            "execution_scope": app.state.store.binding.execution_scope,
            "local_single_operator": True,
        }

    @router.get("/api/handoffs")
    def handoffs():
        return {"records": app.state.store.records()}

    @router.get("/api/policy/evidence")
    def policy_evidence():
        if getattr(app.state.enforcement, "mode", "MOCK") == "LIVE":
            return {"events": app.state.enforcement.audit.events(), "mode": "LIVE"}
        return {"events": app.state.store.policy_evidence(), "mode": "MOCK"}

    @router.post("/api/policy/test", response_model=PolicyResponse)
    async def policy_test(body: PolicyRequest):
        if getattr(app.state.enforcement, "mode", "MOCK") == "LIVE":
            if body.operation != "purge_incident_history":
                return JSONResponse(
                    {
                        "error": {
                            "code": "CORE_DENIED",
                            "message": "Writes require core approval and authorization.",
                        }
                    },
                    status_code=403,
                )
            result = await app.state.enforcement.canary()
            return JSONResponse(
                result, status_code=403 if result["policy_denial_verified"] else 200
            )
        binding = app.state.store.binding
        spec = ExecutionSpec(
            body.operation,
            binding.tool_version,
            binding.target,
            fixture_plan("INC-1042")["steps"][0]["arguments"],
            binding.adapter_id,
            binding.binding_revision,
            binding.execution_scope,
            EXTERNAL_PAYLOAD_REVISION,
        )
        decision = await app.state.enforcement.check(
            spec, approved_payload_digest=spec.payload_digest()
        )
        app.state.store.record_policy(body.operation, decision)
        result = PolicyResponse(
            operation=body.operation, status=decision.status.value, reason=decision.reason
        )
        return JSONResponse(
            result.model_dump(),
            status_code=403 if decision.status == EnforcementStatus.DENIED else 200,
        )

    app.include_router(router)
