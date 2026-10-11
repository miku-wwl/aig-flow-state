import base64
import json

import httpx
import pytest
from armoriq_sdk import ArmorIQClient
from armoriq_sdk.cli import _register_with_control_plane
from armoriq_sdk.config import load_armoriq_config
from fastapi.testclient import TestClient

from safeops.integration.dispatch_permit import load_store, provision_live
from safeops.integration.live_armoriq import safe_failure
from safeops.mcp.server import PROTOCOL_VERSIONS, create_mcp_app
from scripts.diagnose_mcp_discovery import check_url, parse_sse, probe_endpoint
from tests.test_live_armoriq import signed_params


def protected(state, *, diagnostics=False):
    provision_live(state)
    bearer = (state / "armoriq/mcp.bearer").read_text("ascii")
    return TestClient(create_mcp_app(state, diagnostics=diagnostics)), bearer


@pytest.mark.parametrize("version", [*PROTOCOL_VERSIONS, "2099-01-01"])
def test_protocol_negotiates_supported_version_with_exact_id(state, version):
    client, bearer = protected(state)
    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer " + bearer},
        json={
            "jsonrpc": "2.0",
            "id": "exact-id",
            "method": "initialize",
            "params": {"protocolVersion": version},
        },
    )
    assert response.status_code == 200
    result = parse_sse(response.text, "exact-id")
    assert result["protocolVersion"] == (
        version if version in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[-1]
    )


def test_malformed_auth_rejected_without_secret_logging(state):
    client, bearer = protected(state, diagnostics=True)
    packet = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    for headers in [
        {},
        {"Authorization": "Bearer wrong"},
        {"Authorization": b"Bearer \xff"},
        [("Authorization", "Bearer " + bearer), ("Authorization", "Bearer " + bearer)],
        {"Authorization": "secret-as-scheme"},
    ]:
        assert client.post("/mcp", headers=headers, json=packet).status_code == 401
    response = client.post("/mcp", headers={"Authorization": "Bearer " + bearer}, json=packet)
    assert len(parse_sse(response.text, 1)["tools"]) == 2
    logs = (state / "armoriq/mcp-diagnostics.jsonl").read_text("utf-8")
    rows = [json.loads(line) for line in logs.splitlines()]
    assert [row["auth_outcome"] for row in rows] == [*(["DENIED"] * 5), "ALLOWED"]
    assert rows[-1]["correlation_id"] == response.headers["X-Aegis-Correlation-Id"]
    assert rows[2]["auth_scheme"] == "bearer" and rows[4]["auth_scheme"] == "other"
    for secret in [bearer, "secret-as-scheme", "Bearer wrong"]:
        assert secret not in logs


def test_unsupported_or_duplicate_protocol_header_is_http_400(state):
    client, bearer = protected(state)
    for versions in [["2099-01-01"], ["2025-06-18", "2025-06-18"]]:
        response = client.post(
            "/mcp",
            headers=[
                ("Authorization", "Bearer " + bearer),
                *[("MCP-Protocol-Version", version) for version in versions],
            ],
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert response.status_code == 400


def test_discovery_independent_parser_and_valid_schemas(state):
    client, bearer = protected(state)
    result = probe_endpoint(client, "http://127.0.0.1/mcp", bearer)
    assert result["status"] == "PASS" and result["tool_count"] == 2
    assert all(row["http_status"] in {200, 202, 401} for row in result["requests"])
    assert bearer not in json.dumps(result)


@pytest.mark.parametrize(
    "body,identifier",
    [
        ('event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n', 1),
        ('event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{}}\n\n', 1),
        ('event: message\ndata: {"jsonrpc":"2.0","id":1,"error":{}}\n\n', 1),
        ('{"jsonrpc":"2.0","id":1,"result":{}}', 1),
    ],
)
def test_plain_200_bad_sse_error_or_wrong_id_is_not_discovery(body, identifier):
    with pytest.raises(ValueError):
        parse_sse(body, identifier)


def test_invalid_rpc_ids_or_notification_cannot_write_or_leak(state):
    client, bearer = protected(state, diagnostics=True)
    args = signed_params(state)
    for identifier in [None, True, ["secret-in-invalid-id"]]:
        response = client.post(
            "/mcp",
            headers={"Authorization": "Bearer " + bearer},
            json={
                "jsonrpc": "2.0",
                "id": identifier,
                "method": "tools/call",
                "params": {"name": "create_incident_handoff", "arguments": args},
            },
        )
        assert "error" in response.text and "secret-in-invalid-id" not in response.text
    assert not load_store(state).records()
    logs = (state / "armoriq/mcp-diagnostics.jsonl").read_text("utf-8")
    assert bearer not in logs and args["_dispatch"]["signature"] not in logs
    assert "secret-in-invalid-id" not in logs


def test_diagnostic_does_not_call_tools_or_follow_redirects(state):
    _, bearer = protected(state)
    requests = []

    def transport(request):
        requests.append(json.loads(request.content)["method"])
        return httpx.Response(302, headers={"Location": "https://other.example/mcp"})

    with httpx.Client(transport=httpx.MockTransport(transport), follow_redirects=False) as client:
        result = probe_endpoint(client, "http://127.0.0.1/mcp", bearer)
    assert result["status"] == "FAIL"
    assert set(requests) <= {"initialize", "notifications/initialized", "tools/list"}


@pytest.mark.parametrize(
    "url",
    [
        "https://secret@example.com/mcp",
        "https://example.com/mcp?token=secret",
        "http://public.example/mcp",
        "https://example.com/api",
    ],
)
def test_diagnostic_url_boundary(url):
    with pytest.raises(ValueError):
        check_url(url)


def test_actual_cli_register_payload_retains_environment_reference(monkeypatch):
    config = load_armoriq_config("armoriq.yaml")
    monkeypatch.setenv("ARMORIQ_API_KEY", "ak_test_offline_only")
    monkeypatch.setenv("SAFEOPS_MCP_BEARER", "offline-service-secret")
    captured = {}
    actual = httpx.Client

    def transport(request):
        captured["payload"] = json.loads(request.content)
        assert request.headers["Authorization"] == "Bearer ak_test_offline_only"
        return httpx.Response(200, json={"success": True})

    monkeypatch.setattr(
        "armoriq_sdk.cli.httpx.Client",
        lambda **kwargs: actual(transport=httpx.MockTransport(transport), **kwargs),
    )
    _register_with_control_plane(config)
    assert captured["payload"]["mcp_servers"][0]["auth"] == {
        "type": "bearer",
        "token": "$SAFEOPS_MCP_BEARER",
    }
    assert "offline-service-secret" not in json.dumps(captured)


def test_actual_sdk_proxy_mcp_auth_header_is_separate_from_api_auth(state):
    from safeops.configuration import Settings
    from safeops.main import create_app
    from tests.armoriq_harness import offline_live
    from tests.conftest import approved_action

    offline = offline_live(state)
    bearer = (state / "armoriq/mcp.bearer").read_text("ascii")
    sdk = offline.live.client
    sdk.close()
    sdk = ArmorIQClient(
        api_key="ak_test_offline_only",
        max_retries=0,
        timeout=2,
        mcp_credentials={"aegis-relay-mcp": {"authType": "bearer", "token": bearer}},
        _skip_api_key_validation=True,
    )
    captured = []

    def transport(request):
        if request.url.path == "/invoke":
            credential = json.loads(base64.b64decode(request.headers["X-Armoriq-MCP-Auth"]))
            assert credential == {"authType": "bearer", "token": bearer}
            assert request.headers["X-API-Key"] == "ak_test_offline_only"
            captured.append(True)
        return offline.proxy.transport(request)

    sdk.http_client.close()
    sdk.http_client = httpx.Client(transport=httpx.MockTransport(transport))
    from safeops.integration.live_armoriq import LiveArmorIQExecution

    offline.live = LiveArmorIQExecution(
        state, load_store(state), client=sdk, user_email="offline@example.test", offline_test=True
    )
    settings = Settings(
        state=state, provider="fixture", enforcement_mode="real", predecessor_stopped=True
    )
    with TestClient(
        create_app(settings, enforcement=offline.live),
        base_url="http://127.0.0.1",
        headers={"Authorization": "Bearer " + (state / "capability").read_text("ascii")},
    ) as client:
        _, action = approved_action(client)
        from tests.conftest import command_headers

        result = client.post(
            f"/api/actions/{action['action_id']}/execute",
            headers=command_headers(),
            json={"expected_action_version": action["version"]},
        ).json()
        assert result["action"]["state"] == "Succeeded" and captured == [True]
        event = offline.live.audit.events()[-1]
        assert set(event["diagnostics"]["timings_ms"]) == {"CAPTURE", "TOKEN", "PROXY", "RECEIPT"}
        assert [row["http_status"] for row in event["diagnostics"]["http_events"]] == [200, 200]
        assert bearer not in json.dumps(event)


def test_exception_diagnostics_never_serialize_provider_secret():
    from armoriq_sdk.exceptions import MCPInvocationException

    error = MCPInvocationException("provider-secret", status_code=502)
    error.__cause__ = httpx.ReadTimeout("more-provider-secrets")
    diagnostic = safe_failure(error)
    assert diagnostic == {"type": "MCPInvocationException", "http_status": 502, "timeout": True}
    assert "secret" not in json.dumps(diagnostic)
