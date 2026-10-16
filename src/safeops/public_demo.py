"""Consumer-owned public sandbox facade; never composes a live ArmorIQ executor.

Every visitor has a separate mock Runtime and private server-side capability.
The original operator application, Core routes and schemas remain unchanged.
"""

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from safeops.configuration import Settings
from safeops.integration.runtime_composition import private_directory, provision
from safeops.main import STATIC, create_app

COOKIE = "__Host-aegis-demo"
SESSION_AGE = 6 * 86400
HISTORY = [
    {
        "label": "Historical genuine remote ArmorIQ Allow",
        "detail": (
            "Phase 2.4 SDK-only tool-policy Allow; local integrity and Core receipt are separate."
        ),
        "source": "https://github.com/miku-wwl/aig-flow-state/blob/main/docs/phase24-application-e2e-report.md",
    },
    {
        "label": "Historical genuine remote ArmorIQ Deny / Blocked",
        "detail": "Preserved Phase 2.2 purge denial. No fresh canary is dispatched by this demo.",
        "source": "https://github.com/miku-wwl/aig-flow-state/blob/main/docs/phase22-sdk-only-feasibility.md",
    },
]
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
ALLOWED = {
    "GET": [
        r"/api/handoffs",
        r"/api/policy/evidence",
        rf"/api/runs/{UUID}",
        rf"/api/runs/{UUID}/actions",
        rf"/api/actions/{UUID}",
    ],
    "POST": [
        r"/api/runs",
        rf"/api/runs/{UUID}/approval",
        rf"/api/runs/{UUID}/actions",
        rf"/api/actions/{UUID}/authorize",
        rf"/api/actions/{UUID}/execute",
        r"/api/policy/test",
    ],
}


def provision_public(directory):
    root = Path(directory).resolve()
    private_directory(root)
    (root / "sessions").mkdir(mode=0o700)
    with (root / "demo.key").open("xb") as stream:
        stream.write(secrets.token_bytes(32))
    (root / "demo.key").chmod(0o600)
    with sqlite3.connect(root / "demo.sqlite3") as db:
        db.executescript("""
            CREATE TABLE sessions (id TEXT PRIMARY KEY, created INTEGER NOT NULL) STRICT;
            CREATE TABLE quotas (key TEXT NOT NULL, window INTEGER NOT NULL,
                used INTEGER NOT NULL, PRIMARY KEY(key,window)) STRICT;
        """)


@contextmanager
def owner_lock(root):
    with (root / "demo.owner").open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if __import__("os").name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if __import__("os").name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def denied(code, status=403):
    return JSONResponse(
        {"error": {"code": code, "message": "Public sandbox request denied."}}, status_code=status
    )


class PublicSandbox:
    def __init__(self, root, origin, *, provider="deepseek", provider_factory=None):
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.netloc != parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or not re.fullmatch(r"[a-z0-9.-]+", parsed.hostname)
        ):
            raise ValueError("One canonical HTTPS hostname without port/path is required")
        if provider not in {"deepseek", "fixture"}:
            raise ValueError("Public demo supports explicit DeepSeek or offline fixture only")
        self.root, self.origin, self.host = Path(root).resolve(), origin, parsed.hostname
        self.key = (self.root / "demo.key").read_bytes()
        if len(self.key) != 32 or not (self.root / "demo.sqlite3").is_file():
            raise ValueError("Explicitly initialize new public sandbox state once")
        self.provider, self.provider_factory = provider, provider_factory
        self.locks, self.planning = {}, asyncio.Lock()

    def digest(self, text):
        return hmac.new(self.key, text.encode(), hashlib.sha256).hexdigest()

    def quota(self, limits):
        with sqlite3.connect(self.root / "demo.sqlite3", timeout=2) as db:
            db.execute("BEGIN IMMEDIATE")
            for key, window, limit in limits:
                row = db.execute(
                    "SELECT used FROM quotas WHERE key=? AND window=?", (key, window)
                ).fetchone()
                if row and row[0] >= limit:
                    return False
            for key, window, _ in limits:
                db.execute(
                    "INSERT INTO quotas VALUES (?,?,1) "
                    "ON CONFLICT(key,window) DO UPDATE SET used=used+1",
                    (key, window),
                )
        return True

    def session(self, request):
        token = request.cookies.get(COOKIE, "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            return None
        sid = self.digest("session:" + token)
        with sqlite3.connect(self.root / "demo.sqlite3") as db:
            row = db.execute("SELECT created FROM sessions WHERE id=?", (sid,)).fetchone()
        if not row or time.time() - row[0] > SESSION_AGE:
            return None
        return sid, self.digest("csrf:" + token)

    def start(self, request):
        current = self.session(request)
        if current:
            return JSONResponse({"demo_csrf": current[1], "simulation": True})
        ip = self.digest("ip:" + (request.client.host if request.client else "unknown"))
        if not self.quota([("new:" + ip, int(time.time()) // 86400, 8), ("sessions", 0, 80)]):
            return denied("DEMO_SESSION_LIMIT", 429)
        token = secrets.token_urlsafe(32)
        sid = self.digest("session:" + token)
        provision(self.root / "sessions" / sid)
        with sqlite3.connect(self.root / "demo.sqlite3") as db:
            db.execute("INSERT INTO sessions VALUES (?,?)", (sid, int(time.time())))
        response = JSONResponse({"demo_csrf": self.digest("csrf:" + token), "simulation": True})
        response.set_cookie(
            COOKIE,
            token,
            secure=True,
            httponly=True,
            samesite="strict",
            path="/",
            max_age=SESSION_AGE,
        )
        return response

    async def forward(self, request, sid, body):
        settings = Settings(
            state=self.root / "sessions" / sid, provider=self.provider, predecessor_stopped=True
        )
        model = self.provider_factory() if self.provider_factory else None
        # No caller-controlled settings, executable registry or live enforcement.
        inner = create_app(settings, provider=model)
        cap = (settings.state / "capability").read_text("ascii")
        headers = {"Authorization": "Bearer " + cap}
        if request.method == "POST":
            headers["Content-Type"] = "application/json"
        idem = request.headers.getlist("idempotency-key")
        if idem:
            if len(idem) != 1 or len(idem[0]) > 128:
                return denied("DEMO_BAD_COMMAND", 400)
            headers["Idempotency-Key"] = idem[0]
        async with inner.router.lifespan_context(inner):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=inner),
                base_url="http://127.0.0.1",
                trust_env=False,
            ) as client:
                result = await client.request(
                    request.method, request.url.path, headers=headers, content=body
                )
        if request.url.path == "/api/status":
            data = result.json()
            data.update(
                public_demo=True, demo_csrf=self.session(request)[1], historical_evidence=HISTORY
            )
            data["enforcement_label"] = (
                "PUBLIC SIMULATION — synthetic local effects; no ArmorIQ requests"
            )
            return JSONResponse(data, status_code=result.status_code)
        return Response(
            result.content, status_code=result.status_code, media_type="application/json"
        )

    async def handle(self, request):
        path = request.url.path
        if request.url.query or request.headers.getlist("authorization"):
            return denied("DEMO_PRIVILEGED_ACCESS_DENIED")
        origin = request.headers.get("origin")
        if origin and origin != self.origin or request.method == "POST" and origin != self.origin:
            return denied("ORIGIN_DENIED")
        ip = self.digest("ip:" + (request.client.host if request.client else "unknown"))
        if not self.quota(
            [
                ("requests:" + ip, int(time.time()) // 60, 90),
                ("requests:day", int(time.time()) // 86400, 5000),
            ]
        ):
            return denied("DEMO_RATE_LIMIT", 429)
        if request.method == "GET" and path == "/api/health":
            return JSONResponse(
                {"status": "ok", "product": "Aegis Relay", "public_demo": True, "simulation": True}
            )
        if request.method == "GET" and path == "/api/demo/evidence":
            return JSONResponse(
                {"historical": True, "current_execution": "SIMULATION", "evidence": HISTORY}
            )
        session = self.session(request)
        if request.method == "GET" and path == "/api/status" and not session:
            return JSONResponse(
                {
                    "public_demo": True,
                    "execution_path": "mock",
                    "enforcement": "MOCK",
                    "execution_scope": None,
                    "provider": {
                        "mode": self.provider,
                        "model": "deepseek-flash" if self.provider == "deepseek" else None,
                    },
                    "enforcement_label": "PUBLIC SIMULATION — start an isolated demo session",
                    "historical_evidence": HISTORY,
                }
            )
        if request.method not in {"GET", "POST"}:
            return denied("DEMO_ROUTE_DENIED")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 8192:
                return denied("DEMO_REQUEST_TOO_LARGE", 413)
        if request.method == "POST" and path == "/api/demo/session":
            if request.headers.get("x-aegis-demo") != "1" or bytes(raw) != b"{}":
                return denied("DEMO_SESSION_REQUEST_DENIED")
            return self.start(request)
        if not session:
            return denied("DEMO_SESSION_REQUIRED", 401)
        if path != "/api/status" and not any(
            re.fullmatch(pattern, path) for pattern in ALLOWED[request.method]
        ):
            return denied("DEMO_ROUTE_DENIED")
        sid, csrf = session
        if request.method == "POST" and not hmac.compare_digest(
            request.headers.get("x-aegis-csrf", ""), csrf
        ):
            return denied("DEMO_CSRF_DENIED")
        is_plan = request.method == "POST" and path == "/api/runs"
        if is_plan:
            try:
                data = json.loads(raw)
                assert type(data) is dict and set(data) == {"text"}
                assert type(data["text"]) is str and 1 <= len(data["text"]) <= 1500
                assert re.search(r"\bINC-[0-9]{1,12}\b", data["text"])
            except (ValueError, TypeError, AssertionError):
                return denied("DEMO_SYNTHETIC_INPUT_REQUIRED", 400)
            if self.planning.locked():
                return denied("DEMO_PLANNING_BUSY", 429)
        async with self.locks.setdefault(sid, asyncio.Lock()):
            if is_plan:
                async with self.planning:
                    limits = [
                        ("plans:" + sid, 0, 4),
                        ("plans:day", int(time.time()) // 86400, 40),
                        ("plans:total", 0, 160),
                    ]
                    if not self.quota(limits):
                        return denied("DEMO_PLAN_LIMIT", 429)
                    return await self.forward(request, sid, bytes(raw))
            return await self.forward(request, sid, bytes(raw))


def create_public_app(root, origin, *, provider="deepseek", provider_factory=None):
    sandbox = PublicSandbox(root, origin, provider=provider, provider_factory=provider_factory)

    @asynccontextmanager
    async def lifespan(app):
        with owner_lock(sandbox.root):
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[sandbox.host], www_redirect=False)

    @app.middleware("http")
    async def secure(request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            response = denied("DEMO_UNAVAILABLE", 503)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Strict-Transport-Security": "max-age=604800",
                "Content-Security-Policy": (
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; "
                    "base-uri 'none'; form-action 'self'"
                ),
            }
        )
        return response

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="public-static")

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    async def api(request: Request, path: str):
        return await sandbox.handle(request)

    return app


def main():
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(
        description="Isolated public simulation; no live ArmorIQ executor"
    )
    parser.add_argument("command", choices=["init", "serve"])
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--origin")
    parser.add_argument("--provider", choices=["deepseek", "fixture"], default="deepseek")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--predecessor-stopped", action="store_true")
    args = parser.parse_args()
    if args.command == "init":
        provision_public(args.state)
        print("Initialized NEW private public-demo control state; no model or ArmorIQ requests.")
        return
    if not args.predecessor_stopped or not args.origin:
        parser.error(
            "Existing state, canonical HTTPS origin and --predecessor-stopped are required"
        )
    uvicorn.run(
        create_public_app(args.state, args.origin, provider=args.provider),
        host="127.0.0.1",
        port=args.port,
        workers=1,
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )


if __name__ == "__main__":
    main()
