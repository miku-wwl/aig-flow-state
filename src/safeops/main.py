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

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
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
                    request.app.state.runtime.verifier.verify(
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
        response = await call_next(request)
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
    parser = argparse.ArgumentParser(description="SafeOps Agent local single-operator demo")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Exclusively provision a NEW private state directory")
    init.add_argument("--state", type=Path, default=Path(".runtime/local"))
    serve = commands.add_parser("serve", help="Serve an already initialized local runtime")
    serve.add_argument("--state", type=Path)
    serve.add_argument("--provider", choices=["ollama", "fixture"])
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
    )
    uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
