import copy
import hmac
import json
import time
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from jsonschema import Draft202012Validator

from safeops.domain.handoff import ARGUMENT_SCHEMA
from safeops.integration.armoriq_mapping import CANARY
from safeops.integration.dispatch_permit import (
    DispatchDeadline,
    PermitVerifier,
    live_directory,
    load_store,
)

PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")
RPC_METHODS = {"initialize", "notifications/initialized", "tools/list", "tools/call"}


def create_mcp_app(state, *, lose_ack=False, diagnostics=False):
    store = load_store(state)
    directory = live_directory(state, store)
    verifier = PermitVerifier(directory, store)
    bearer = (directory / "mcp.bearer").read_text("ascii")
    if len(bearer) != 64:
        raise ValueError("Invalid service bearer")
    schema = copy.deepcopy(ARGUMENT_SCHEMA)
    schema["required"].append("_dispatch")
    schema["properties"]["_dispatch"] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["body", "signature"],
        "properties": {
            "body": {"type": "object"},
            "signature": {"type": "string", "minLength": 88, "maxLength": 88},
        },
    }
    canary_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["probe_id"],
        "properties": {"probe_id": {"type": "string", "minLength": 36, "maxLength": 36}},
    }
    tools = [
        {
            "name": store.binding.tool_name,
            "description": "Persist one signed reviewed handoff",
            "inputSchema": schema,
        },
        {
            "name": CANARY,
            "description": "Nondestructive boundary canary; never deletes data",
            "inputSchema": canary_schema,
        },
    ]
    app = FastAPI(
        title="Aegis Relay protected MCP", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.store = store

    if diagnostics:

        @app.middleware("http")
        async def diagnostic_request(request: Request, call_next):
            started = time.perf_counter()
            auth = request.headers.getlist("authorization")
            scheme = auth[0].split(" ", 1)[0].lower() if len(auth) == 1 else "other"
            # Closed values only: even a header consisting solely of a secret is not logged.
            record = {
                "correlation_id": str(uuid4()),
                "created_at": datetime.now(UTC).isoformat(),
                "http_method": request.method if request.method in {"POST", "GET"} else "other",
                "route": "/mcp" if request.url.path == "/mcp" else "other",
                "authorization_present": bool(auth),
                "authorization_count": min(len(auth), 2),
                "auth_scheme": scheme if scheme in {"bearer", "basic"} else "other",
                "auth_outcome": "NOT_CHECKED",
                "rpc_method": "unknown",
                "rpc_outcome": "NOT_PARSED",
            }
            request.state.diagnostic = record
            try:
                response = await call_next(request)
                record["http_status"] = response.status_code
                response.headers["X-Aegis-Correlation-Id"] = record["correlation_id"]
                return response
            finally:
                record["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
                # The directory was explicitly provisioned as private. No request values,
                # payloads, signatures, exception messages or credentials are serialized.
                with (directory / "mcp-diagnostics.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record) + "\n")

    @app.post("/mcp")
    async def mcp(request: Request):
        diagnostic = getattr(request.state, "diagnostic", {})
        auth = request.headers.getlist("authorization")
        if len(auth) != 1 or not hmac.compare_digest(
            auth[0].encode("utf-8"), ("Bearer " + bearer).encode("ascii")
        ):
            diagnostic["auth_outcome"] = "DENIED"
            return JSONResponse({"error": "SERVICE_AUTH_REQUIRED"}, status_code=401)
        diagnostic["auth_outcome"] = "ALLOWED"
        if request.headers.get("origin"):
            return JSONResponse({"error": "BROWSER_ACCESS_DENIED"}, status_code=403)
        versions = request.headers.getlist("mcp-protocol-version")
        if versions and (len(versions) != 1 or versions[0] not in PROTOCOL_VERSIONS):
            return JSONResponse({"error": "UNSUPPORTED_PROTOCOL_VERSION"}, status_code=400)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 16384:
                return JSONResponse({"error": "REQUEST_TOO_LARGE"}, status_code=413)
        msg_id = None
        try:
            value = json.loads(raw)
            if (
                type(value) is not dict
                or value.get("jsonrpc") != "2.0"
                or set(value) - {"jsonrpc", "id", "method", "params"}
            ):
                raise ValueError("Invalid RPC envelope")
            identifier = value.get("id")
            if type(identifier) not in {int, str, type(None)}:
                raise ValueError("Invalid RPC identifier")
            msg_id = identifier
            method, params = value["method"], value.get("params", {})
            diagnostic["rpc_method"] = method if method in RPC_METHODS else "unknown"
            if type(params) is not dict:
                raise ValueError("Invalid RPC parameters")
            if method == "notifications/initialized" and msg_id is None:
                diagnostic["rpc_outcome"] = "ACCEPTED_NOTIFICATION"
                return Response(status_code=202)
            if msg_id is None:
                raise ValueError("Tool requests require an identifier")
            if method == "initialize":
                version = params.get("protocolVersion")
                if type(version) is not str or not 1 <= len(version) <= 32:
                    raise ValueError("Invalid protocol version")
                result = {
                    "protocolVersion": version
                    if version in PROTOCOL_VERSIONS
                    else PROTOCOL_VERSIONS[-1],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "aegis-relay-mcp", "version": "0.1.0"},
                }
            elif method == "tools/list":
                result = {"tools": tools}
            elif method == "tools/call":
                if type(params) is not dict or set(params) != {"name", "arguments"}:
                    raise ValueError("Invalid tool call")
                tool = next((tool for tool in tools if tool["name"] == params["name"]), None)
                if tool is None:
                    raise ValueError("Unregistered tool")
                Draft202012Validator(tool["inputSchema"]).validate(params["arguments"])
                if tool["name"] == CANARY:
                    result = {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "classification": "CANARY_NONDESTRUCTIVE",
                                        "business_effect": False,
                                    }
                                ),
                            }
                        ],
                    }
                else:
                    started = time.perf_counter()
                    spec, body = verifier.verify(params["arguments"])
                    diagnostic["permit_verify_ms"] = round(
                        (time.perf_counter() - started) * 1000, 3
                    )
                    diagnostic["action_id"] = body["action_id"]
                    diagnostic["effect_key"] = body["effect_key"]
                    started = time.perf_counter()
                    receipt = store.persist(
                        spec,
                        body["effect_key"],
                        DispatchDeadline(body["expires_at"]),
                        lose_ack=lose_ack,
                    )
                    diagnostic["business_write_ms"] = round(
                        (time.perf_counter() - started) * 1000, 3
                    )
                    data = {
                        name: body[name]
                        for name in (
                            "action_id",
                            "effect_key",
                            "payload_digest",
                            "store_id",
                            "binding",
                            "service",
                        )
                    } | {"receipt_reference": receipt}
                    result = {"content": [{"type": "text", "text": json.dumps(data)}]}
            else:
                raise ValueError("Unsupported method")
            payload = {"jsonrpc": "2.0", "id": msg_id, "result": result}
            diagnostic["rpc_outcome"] = "RESULT"
        except Exception:
            diagnostic["rpc_outcome"] = "ERROR_UNCONFIRMED"
            # A commit acknowledgement may be lost; never report this as proven no effect.
            payload = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32001,
                    "message": "Protected request rejected or outcome unconfirmed",
                },
            }
        return Response(
            "event: message\ndata: " + json.dumps(payload) + "\n\n",
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store"},
        )

    return app
