from typing import Literal

from agentic_intent_gate.runtime import EXTERNAL_PAYLOAD_REVISION, ExecutionSpec
from fastapi import APIRouter, Request
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


def stage_error():
    return JSONResponse(
        {
            "error": {
                "code": "SDK_PRESTAGE_DENIED",
                "message": (
                    "Exact Authorized Action and version required. No automatic preparation retry."
                ),
            }
        },
        status_code=409,
    )


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
        sdk_only = live and live_status.get("path") == "sdk-only"
        label = (
            "Offline SDK test transport — no real platform enforcement"
            if live and live_status["transport"] == "OFFLINE_TEST"
            else "ARMORIQ SDK-ONLY LIVE — remote tool policy, local verified execution"
            if sdk_only
            else "PROXY LIVE — real ArmorIQ proxy execution; qualification pending"
            if live
            else "Simulated policy enforcement — Phase 1 offline mode"
        )
        return {
            "provider": app.state.provider.status(),
            "enforcement": "LIVE" if live else "MOCK",
            "enforcement_label": label,
            "execution_path": "sdk-only" if sdk_only else "proxy" if live else "mock",
            "armoriq": {key: value for key, value in live_status.items() if key != "last_event"}
            if live
            else None,
            "execution_scope": app.state.store.binding.execution_scope,
            "local_single_operator": True,
        }

    @router.get("/api/handoffs")
    def handoffs():
        return {"records": app.state.store.records()}

    @router.get("/api/actions/{action_id}/sdk-stage")
    def sdk_stage(action_id: str, request: Request):
        if getattr(app.state.enforcement, "path", None) != "sdk-only":
            return JSONResponse({"error": {"code": "SDK_MODE_REQUIRED"}}, status_code=409)
        try:
            principal = app.state.runtime.verifier.verify(request.headers.get("authorization"))
            return app.state.enforcement.stage_status(action_id, principal)
        except Exception:
            return stage_error()

    @router.post("/api/actions/{action_id}/sdk-stage")
    async def prepare_sdk_stage(action_id: str, request: Request):
        if getattr(app.state.enforcement, "path", None) != "sdk-only":
            return JSONResponse({"error": {"code": "SDK_MODE_REQUIRED"}}, status_code=409)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 1024:
                return stage_error()
        try:
            import json

            body = json.loads(raw)
            if (
                type(body) is not dict
                or set(body) != {"expected_action_version"}
                or type(body["expected_action_version"]) is not int
                or body["expected_action_version"] < 1
            ):
                return stage_error()
            principal = app.state.runtime.verifier.verify(request.headers.get("authorization"))
            return await app.state.enforcement.prepare(
                action_id, principal, body["expected_action_version"]
            )
        except Exception:
            return stage_error()

    @router.get("/api/policy/evidence")
    def policy_evidence():
        if getattr(app.state.enforcement, "mode", "MOCK") == "LIVE":
            return {"events": app.state.enforcement.audit.events(), "mode": "LIVE"}
        return {"events": app.state.store.policy_evidence(), "mode": "MOCK"}

    @router.post("/api/policy/test", response_model=PolicyResponse)
    async def policy_test(body: PolicyRequest):
        if getattr(app.state.enforcement, "path", None) == "sdk-only":
            return JSONResponse(
                {
                    "mode": "LIVE",
                    "source": "Historical Phase 2.2 evidence; no fresh request",
                    "operation": body.operation,
                    "status": "NOT_RUN_IN_PHASE24",
                    "historical_request_id": "a1d37130-5f82-4e91-a752-6f58c9172f59",
                    "core_action_created": False,
                    "business_effect_executed": False,
                },
                status_code=409,
            )
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
