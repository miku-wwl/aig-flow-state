"""One real forwarded execution, followed by independent durable receipt verification."""

import asyncio
import os
import time
from datetime import UTC, datetime
from uuid import UUID

import httpx
from agentic_intent_gate.runtime import Outcome, ToolOutcome
from armoriq_sdk import ArmorIQClient
from armoriq_sdk.credentials import load_credentials
from armoriq_sdk.exceptions import (
    IntentMismatchException,
    InvalidTokenException,
    PolicyBlockedException,
    PolicyHoldException,
    TokenExpiredException,
)

from safeops.execution.handoff_store import binding_identity
from safeops.integration.armoriq_mapping import (
    AGENT_NAME,
    CANARY,
    MCP_NAME,
    captured_step,
    receipt_payload,
)
from safeops.integration.dispatch_permit import PermitIssuer, PermitRejected, live_directory
from safeops.integration.live_audit import LiveAudit


def build_client(directory, *, factory=ArmorIQClient):
    creds = load_credentials()
    key = os.getenv("ARMORIQ_API_KEY") or (creds.apiKey if creds else "")
    email = os.getenv("SAFEOPS_ARMORIQ_USER_EMAIL") or (creds.email if creds else "")
    if not key.startswith(("ak_live_", "ak_test_")) or not email or "@" not in email:
        raise ValueError("Real mode requires existing ArmorIQ credentials and operator identity")
    bearer = (directory / "mcp.bearer").read_text("ascii")
    if len(bearer) != 64 or any(c not in "0123456789abcdef" for c in bearer):
        raise ValueError("Invalid private MCP credential")
    try:
        client = factory(
            api_key=key,
            user_id=email,
            agent_id=AGENT_NAME,
            timeout=2,
            max_retries=0,
            verify_ssl=True,
            iap_endpoint="https://iap.armoriq.ai",
            proxy_endpoint="https://proxy.armoriq.ai",
            backend_endpoint="https://api.armoriq.ai",
            mcp_credentials={MCP_NAME: {"authType": "bearer", "token": bearer}},
        )
    except Exception:
        raise ValueError("ArmorIQ client initialization failed; no mock fallback") from None
    # Explicit identity for token issuance and policy/audit attribution.
    client.user_email_override = email
    client.http_client.follow_redirects = False
    return client, email


class LiveArmorIQExecution:
    mode = "LIVE"

    def __init__(self, state, store, *, client=None, user_email=None, offline_test=False):
        directory = live_directory(state, store)
        self.store = store
        self.issuer = PermitIssuer(directory, store)
        self.audit = LiveAudit(directory / "audit.sqlite3")
        self.client, self.user_email = (
            (client, user_email) if client is not None else build_client(directory)
        )
        self.connection = "NOT_PROBED"
        self.registration = "UNVERIFIED"
        self.offline_test = offline_test
        self.http_events = []

        def request_started(request):
            request.extensions["aegis_diagnostic_started"] = time.perf_counter()

        def response_headers(response):
            before = response.request.extensions.get("aegis_diagnostic_started")
            if before is None or len(self.http_events) >= 8:
                return
            path = response.request.url.path
            self.http_events.append(
                {
                    "stage": "TOKEN"
                    if path == "/iap/sdk/token"
                    else "PROXY"
                    if path == "/invoke"
                    else "OTHER",
                    "created_at": datetime.now(UTC).isoformat(),
                    "http_status": response.status_code,
                    "response_headers_ms": round((time.perf_counter() - before) * 1000, 3),
                }
            )

        self.client.http_client.event_hooks["request"].append(request_started)
        self.client.http_client.event_hooks["response"].append(response_headers)

    def close(self):
        self.client.close()

    def status(self):
        events = self.audit.events()
        return {
            "mode": "LIVE",
            "sdk": "0.6.10",
            "connectivity": self.connection,
            "registration": self.registration,
            "transport": "OFFLINE_TEST" if self.offline_test else "REAL_PLATFORM",
            "last_event": events[-1] if events else None,
        }

    def verify_receipt(self, result, spec, permit):
        data = receipt_payload(result)
        body = permit["body"]
        expected = {
            name: body[name]
            for name in (
                "action_id",
                "effect_key",
                "payload_digest",
                "store_id",
                "binding",
                "service",
            )
        }
        if (
            not isinstance(data, dict)
            or set(data) != set(expected) | {"receipt_reference"}
            or any(data[name] != value for name, value in expected.items())
            or str(UUID(data["receipt_reference"], version=4)) != data["receipt_reference"]
        ):
            raise ValueError("Unbound receipt")
        rows = [row for row in self.store.records() if row["effect_key"] == body["effect_key"]]
        if (
            len(rows) != 1
            or rows[0]["payload_digest"] != spec.payload_digest()
            or rows[0]["receipt_reference"] != data["receipt_reference"]
            or rows[0]["store_id"] != self.store.store_id
            or rows[0]["binding_identity"] != binding_identity(self.store.binding)
            or any(rows[0][name] != value for name, value in dict(spec.arguments).items())
        ):
            raise ValueError("Receipt has no matching durable effect")
        return data["receipt_reference"]

    async def execute(self, spec, effect_key, context):
        self.http_events.clear()
        started = time.perf_counter()
        timings = {}
        phase = "PERMIT"
        failure = None

        def measured(name, operation):
            nonlocal phase
            phase = name
            before = time.perf_counter()
            try:
                return operation()
            finally:
                timings[name] = round((time.perf_counter() - before) * 1000, 3)

        def diagnostics():
            return {
                "stage": phase,
                "timings_ms": dict(timings),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "error": safe_failure(failure),
                "http_events": list(self.http_events),
            }

        def outcome(category, receipt=None):
            return ToolOutcome(
                category,
                effect_key,
                spec.execution_scope,
                spec.target,
                spec.payload_digest(),
                receipt,
                "INPUT_REJECTED" if category == Outcome.CONFIRMED_FAILURE else None,
            )

        try:
            permit = self.issuer.issue(spec, effect_key, context)
            plan, params = captured_step(spec, self.store.binding, permit)
        except (PermitRejected, ValueError):
            self.audit.record("CORE_DENIED", effect_key=effect_key)
            return outcome(Outcome.CONFIRMED_FAILURE)
        body = permit["body"]
        stage = "TOKEN"
        token = None

        def dispatch():
            nonlocal stage, token
            capture = measured(
                "CAPTURE",
                lambda: self.client.capture_plan(
                    llm="core-approved-plan",
                    prompt="Execute the exact reviewed incident handoff",
                    plan=plan,
                    metadata={"action_id": body["action_id"]},
                ),
            )
            token = measured(
                "TOKEN", lambda: self.client.get_intent_token(capture, validity_seconds=10)
            )
            if context.cancelled.is_set() or time.time() >= body["expires_at"]:
                raise TimeoutError("Dispatch expired before forwarding")
            stage = "INVOKE"
            return measured(
                "PROXY",
                lambda: self.client.invoke(
                    MCP_NAME, spec.tool_name, token, params=params, user_email=self.user_email
                ),
            )

        classification, category, receipt = "UNAVAILABLE", Outcome.UNKNOWN_OUTCOME, None
        try:
            result = await asyncio.to_thread(dispatch)
            stage = "RECEIPT"
            receipt = measured("RECEIPT", lambda: self.verify_receipt(result, spec, permit))
            classification, category = "ALLOWED_VERIFIED", Outcome.SUCCESS
            self.connection = "RESPONSE_RECEIVED"
        except PolicyBlockedException as exc:
            failure = exc
            classification = policy_denial_class(exc, spec.tool_name)
            category = Outcome.CONFIRMED_FAILURE
        except PolicyHoldException as exc:
            failure = exc
            classification, category = "ARMORIQ_POLICY_HOLD", Outcome.CONFIRMED_FAILURE
        except (IntentMismatchException, TokenExpiredException) as exc:
            failure = exc
            classification = "INTENT_MISMATCH"
            category = Outcome.CONFIRMED_FAILURE
        except InvalidTokenException as exc:
            failure = exc
            classification = wrapped_failure(exc, stage)
            category = Outcome.CONFIRMED_FAILURE
        except (TimeoutError, httpx.TimeoutException) as exc:
            failure = exc
            classification = "TIMEOUT"
            category = Outcome.CONFIRMED_FAILURE if stage == "TOKEN" else Outcome.UNKNOWN_OUTCOME
        except asyncio.CancelledError as exc:
            failure = exc
            self.audit.record(
                "TIMEOUT",
                action_id=body["action_id"],
                effect_key=effect_key,
                diagnostics=diagnostics(),
            )
            raise
        except Exception as exc:
            failure = exc
            classification = wrapped_failure(exc, stage)
            category = Outcome.CONFIRMED_FAILURE if stage == "TOKEN" else Outcome.UNKNOWN_OUTCOME
        plan_id = getattr(token, "plan_id", None)
        # Correlation IDs only; never save raw tokens or exception bodies.
        if (
            not isinstance(plan_id, str)
            or len(plan_id) > 128
            or not all(c.isalnum() or c in "-_" for c in plan_id)
        ):
            plan_id = None
        self.audit.record(
            classification,
            action_id=body["action_id"],
            effect_key=effect_key,
            plan_id=plan_id,
            receipt_reference=receipt,
            diagnostics=diagnostics(),
        )
        return outcome(category, receipt)

    async def canary(self):
        """Separate valid canary plan: never admitted to the core tool registry."""
        params = {"probe_id": str(UUID(bytes=os.urandom(16), version=4))}
        before = self.store.records()
        classification = "UNAVAILABLE"
        try:

            def probe():
                capture = self.client.capture_plan(
                    llm="deterministic-boundary-probe",
                    prompt="Probe the explicit canary deny",
                    plan={"steps": [{"mcp": MCP_NAME, "action": CANARY, "params": params}]},
                )
                token = self.client.get_intent_token(capture, validity_seconds=10)
                return self.client.invoke(
                    MCP_NAME, CANARY, token, params=params, user_email=self.user_email
                )

            await asyncio.wait_for(asyncio.to_thread(probe), timeout=5)
            classification = "CANARY_REACHED_SERVICE"
        except PolicyBlockedException as exc:
            classification = policy_denial_class(exc, CANARY)
        except PolicyHoldException:
            classification = "ARMORIQ_POLICY_HOLD"
        except (IntentMismatchException, TokenExpiredException):
            classification = "INTENT_MISMATCH"
        except (TimeoutError, httpx.TimeoutException):
            classification = "TIMEOUT"
        except Exception as exc:
            classification = wrapped_failure(exc, "TOKEN")
        unchanged = self.store.records() == before
        event = self.audit.record(classification, operation=CANARY)
        return event | {
            "core_action_created": False,
            "business_effect_executed": False,
            "effect_store_unchanged": unchanged,
            "policy_denial_verified": classification == "ARMORIQ_POLICY_DENIED",
        }


def safe_failure(error):
    """Closed exception names and numeric status only; never provider messages/metadata."""
    if error is None:
        return None
    names = {
        "PolicyBlockedException",
        "PolicyHoldException",
        "IntentMismatchException",
        "TokenExpiredException",
        "InvalidTokenException",
        "MCPInvocationException",
        "TimeoutError",
        "ReadTimeout",
        "ConnectTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "ConnectError",
        "RemoteProtocolError",
        "CancelledError",
        "ValueError",
    }
    status = getattr(error, "status_code", None)
    result = {
        "type": type(error).__name__ if type(error).__name__ in names else "OTHER",
        "http_status": status if type(status) is int and 100 <= status <= 599 else None,
    }
    seen = set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (TimeoutError, httpx.TimeoutException)):
            result["timeout"] = True
        current = current.__cause__ or current.__context__
    return result


def wrapped_failure(error, stage):
    """0.6.10 wraps httpx errors; inspect exception types, never log their contents."""
    seen = set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (TimeoutError, httpx.TimeoutException)):
            return "TIMEOUT"
        current = current.__cause__ or current.__context__
    if stage == "RECEIPT":
        return "RECEIPT_INVALID"
    return "TOKEN_FAILURE" if stage == "TOKEN" else "UNAVAILABLE"


def policy_denial_class(error, tool):
    # 0.6.10 maps *any* token-endpoint HTTP 403 to PolicyBlockedException.
    # Require explicit policy fields before presenting it as a policy boundary proof.
    metadata = error.metadata if isinstance(error.metadata, dict) else {}
    denied = metadata.get("denied_tools")
    explicit_tool = isinstance(denied, list) and any(
        item in denied for item in [tool, f"{MCP_NAME}.{tool}"]
    )
    if error.enforcement_action in {"block", "deny"} or explicit_tool:
        return "ARMORIQ_POLICY_DENIED"
    return "SDK_DENIED_UNCLASSIFIED"
