"""Actual SDK + local MCP with a deterministic, OFFLINE proxy transport."""

import json
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
from armoriq_sdk import ArmorIQClient
from fastapi.testclient import TestClient

from safeops.integration.dispatch_permit import provision_live
from safeops.integration.live_armoriq import LiveArmorIQExecution
from safeops.mcp.server import create_mcp_app


class OfflineProxy:
    def __init__(self, state, *, fault="none"):
        self.state, self.fault = state, fault
        self.calls = []
        self.client = TestClient(create_mcp_app(state, lose_ack=fault == "lost_ack"))
        self.bearer = (state / "armoriq" / "mcp.bearer").read_text("ascii")

    def transport(self, request):
        payload = json.loads(request.content) if request.content else {}
        self.calls.append((request.url.path, payload))
        if request.url.path.endswith("/token"):
            if self.fault == "token_403":
                return httpx.Response(403, json={"message": "not authorized"})
            if self.fault == "token_failure":
                return httpx.Response(503, json={"message": "offline token failure"})
            if self.fault == "late_token":
                time.sleep(5.2)
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "plan_id": str(uuid4()),
                    "intent_reference": "offline-reference",
                    "plan_hash": "offline-hash",
                    "token": {},
                    "step_proofs": [[{"offline": True}]],
                },
            )
        if request.url.path == "/invoke":
            if self.fault in {"deny", "hold"}:
                return httpx.Response(
                    403,
                    json={
                        "enforcement": {
                            "action": "block" if self.fault == "deny" else "hold",
                            "reason": "offline",
                        }
                    },
                )
            if self.fault == "mismatch":
                return httpx.Response(409, json={"message": "offline mismatch"})
            if self.fault == "timeout":
                raise httpx.ReadTimeout("offline timeout", request=request)
            if self.fault == "remote_5xx":
                return httpx.Response(502, json={"message": "offline unavailable"})
            if self.fault == "missing_receipt":
                return httpx.Response(200, json={"result": {"content": []}})
            response = self.client.post(
                "/mcp",
                headers={"Authorization": "Bearer " + self.bearer},
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": payload["action"], "arguments": payload["params"]},
                },
            )
            rpc = json.loads(response.text.split("data: ")[1])
            if self.fault == "timeout_after_commit":
                raise httpx.ReadTimeout("offline lost response", request=request)
            if self.fault in {"wrong_receipt", "wrong_digest", "wrong_action"}:
                data = json.loads(rpc["result"]["content"][0]["text"])
                field = {
                    "wrong_receipt": "receipt_reference",
                    "wrong_digest": "payload_digest",
                    "wrong_action": "action_id",
                }[self.fault]
                data[field] = str(uuid4())
                rpc["result"]["content"][0]["text"] = json.dumps(data)
            return httpx.Response(200, json=rpc)
        raise AssertionError("Unexpected network path")

    def sdk(self):
        client = ArmorIQClient(
            api_key="ak_test_offline_only",
            user_id="offline@example.test",
            agent_id="aegis-relay",
            max_retries=0,
            timeout=2,
            _skip_api_key_validation=True,
        )
        client.http_client.close()
        client.http_client = httpx.Client(transport=httpx.MockTransport(self.transport))
        return client


def offline_live(state, *, fault="none"):
    from safeops.integration.dispatch_permit import load_store

    if not (state / "armoriq").exists():
        provision_live(state)
    proxy = OfflineProxy(state, fault=fault)
    live = LiveArmorIQExecution(
        state,
        load_store(state),
        client=proxy.sdk(),
        user_email="offline@example.test",
        offline_test=True,
    )
    return SimpleNamespace(live=live, proxy=proxy)
