import argparse
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from safeops.api.routes import consumer_routes
from safeops.configuration import Settings
from safeops.integration.runtime_composition import composition, provision

STATIC = Path(__file__).parent / "api" / "static"


def create_app(settings, *, provider=None, enforcement=None):
    @asynccontextmanager
    async def lifespan(app):
        with composition(settings, provider=provider, enforcement=enforcement) as parts:
            runtime, store, model, boundary, executor = parts
            app.state.runtime, app.state.store = runtime, store
            app.state.provider, app.state.enforcement, app.state.executor = (
                model,
                boundary,
                executor,
            )
            # Reuse the actual core routes and error/CAS/idempotency contracts unchanged.
            app.mount("/", runtime.http_app(), name="shared-runtime")
            mounted = app.router.routes[-1]
            try:
                yield
            finally:
                app.router.routes.remove(mounted)

    app = FastAPI(
        title="Aegis Relay",
        description="A permissioned AI agent for secure incident handoffs.",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "[::1]"],
        www_redirect=False,
    )

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin:
                expected = urlsplit(str(request.url))
                actual = urlsplit(origin)
                if (
                    actual.scheme != "http"
                    or actual.netloc != expected.netloc
                    or actual.hostname not in {"127.0.0.1", "localhost", "::1"}
                    or actual.path
                    or actual.query
                    or actual.fragment
                    or actual.username
                    or actual.password
                ):
                    return JSONResponse({"error": {"code": "ORIGIN_DENIED"}}, status_code=403)
            if request.url.query:
                return JSONResponse({"error": {"code": "QUERY_DENIED"}}, status_code=400)
            if path not in {"/api/health", "/api/status"}:
                headers = request.headers.getlist("authorization")
                try:
                    principal = request.app.state.runtime.verifier.verify(
                        headers[0] if len(headers) == 1 else None
                    )
                except Exception:
                    return JSONResponse(
                        {
                            "error": {
                                "code": "AUTHENTICATION_REQUIRED",
                                "message": "Load the private capability file.",
                            }
                        },
                        status_code=401,
                    )
                if (
                    getattr(request.app.state.enforcement, "mode", "MOCK") == "LIVE"
                    and request.method == "POST"
                    and path.startswith("/api/actions/")
                    and path.endswith("/execute")
                ):
                    try:
                        # Public read supplies a hint; issuance rechecks the durable claim.
                        boundary = request.app.state.enforcement
                        action_id = path.split("/")[3]
                        if settings.enforcement_mode == "sdk-only":
                            current = request.app.state.runtime.gateway.get(action_id, principal)
                            # Core owns request validation and terminal idempotency replay.
                            # Only a syntactically valid fresh command is stage-gated here.
                            keys = request.headers.getlist("idempotency-key")
                            from agentic_intent_gate.runtime import ActionCommand

                            try:
                                length = request.headers.get("content-length", "")
                                if not length.isdigit() or int(length) > 1024:
                                    raise ValueError
                                body = await request.body()
                                if len(body) > 1024 or len(keys) != 1:
                                    raise ValueError
                                command = ActionCommand.parse(
                                    action_id, body.decode("utf-8"), idempotency_key=keys[0]
                                )
                            except Exception:
                                pass
                            else:
                                if (
                                    current.state.value == "Authorized"
                                    and command.expected_action_version == current.version
                                ):
                                    try:
                                        boundary.require_ready(action_id, principal)
                                    except Exception:
                                        return JSONResponse(
                                            {
                                                "error": {
                                                    "code": "SDK_STAGE_REQUIRED",
                                                    "message": (
                                                        "Prepare the Authorized Action explicitly; "
                                                        "the stage is missing, invalid or expired."
                                                    ),
                                                }
                                            },
                                            status_code=409,
                                        )
                        else:
                            boundary.issuer.track(action_id)
                    except Exception:
                        return JSONResponse({"error": {"code": "CORE_DENIED"}}, status_code=403)
        response = await call_next(request)
        if (
            settings.enforcement_mode == "sdk-only"
            and request.method == "POST"
            and path.startswith("/api/actions/")
            and path.endswith("/execute")
            and response.status_code in {200, 202}
        ):
            try:
                await app.state.enforcement.finalize(path.split("/")[3], principal)
            except Exception:
                # Core's durable terminal result survives consumer audit unavailability.
                pass
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
        )
        return response

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="safeops-static")
    consumer_routes(app)
    return app


def main():
    parser = argparse.ArgumentParser(
        description="Aegis Relay — A permissioned AI agent for secure incident handoffs.",
        epilog="Trust the intent. Govern the action.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Exclusively provision a NEW private state directory")
    init.add_argument("--state", type=Path, default=Path(".runtime/local"))
    init_live = commands.add_parser(
        "init-live", help="Exclusively provision private MCP keys/audit"
    )
    init_live.add_argument("--state", type=Path, default=Path(".runtime/local"))
    mcp = commands.add_parser(
        "mcp", help="Serve only the protected MCP on a separate loopback port"
    )
    mcp.add_argument("--state", type=Path, default=Path(".runtime/local"))
    mcp.add_argument("--port", type=int, default=8766)
    mcp.add_argument("--diagnostics", action="store_true", help="Private sanitized MCP diagnostics")
    serve = commands.add_parser("serve", help="Serve an already initialized local runtime")
    serve.add_argument("--state", type=Path)
    serve.add_argument("--provider", choices=["ollama", "fixture", "deepseek"])
    serve.add_argument("--enforcement-mode", choices=["mock", "real", "proxy", "sdk-only"])
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--predecessor-stopped", action="store_true", required=True)
    serve.add_argument(
        "--fixture-fault",
        choices=["none", "timeout", "invalid_json", "unavailable"],
        default="none",
    )
    serve.add_argument(
        "--executor-fault", choices=["none", "post_commit_ack_loss", "policy_deny"], default="none"
    )
    args = parser.parse_args()
    if args.command == "init-live":
        from safeops.integration.dispatch_permit import provision_live

        provision_live(args.state)
        print("Provisioned private dispatch keys, service bearer and live audit; no cloud changes.")
        return
    if args.command == "mcp":
        from safeops.mcp.server import create_mcp_app

        uvicorn.run(
            create_mcp_app(args.state, diagnostics=args.diagnostics),
            host="127.0.0.1",
            port=args.port,
            access_log=False,
        )
        return
    if args.command == "init":
        provision(args.state)
        print(f"Initialized private state: {args.state.resolve()}")
        print("Capability contents are never printed. Select the capability file in the browser.")
        return
    settings = Settings.from_env(predecessor_stopped=args.predecessor_stopped)
    settings = replace(
        settings,
        state=args.state or settings.state,
        provider=args.provider or settings.provider,
        fixture_fault=args.fixture_fault,
        executor_fault=args.executor_fault,
        enforcement_mode=args.enforcement_mode or settings.enforcement_mode,
    )
    uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
