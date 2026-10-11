"""Bounded read-only MCP discovery. Never registers, mints tokens or calls tools."""

import argparse
import json
import logging
import os
import time
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from armoriq_sdk.cli import discover_mcp_tools
from armoriq_sdk.config import MCPServerConfig
from jsonschema import Draft202012Validator

from safeops.integration.armoriq_mapping import AGENT_NAME, CANARY, MCP_NAME
from safeops.integration.live_armoriq import build_client, safe_failure

EXPECTED_TOOLS = {"create_incident_handoff", CANARY}


def parse_sse(body, expected_id):
    """Independent finite SSE/JSON-RPC parser, with exact response ID checks."""
    if len(body) > 65536:
        raise ValueError("RESPONSE_LIMIT")
    body = body.replace("\r\n", "\n")
    if not body.endswith("\n\n"):
        raise ValueError("INCOMPLETE_SSE")
    messages = []
    for event in body.split("\n\n"):
        data, kind = [], "message"
        for line in event.splitlines():
            if line.startswith(":") or not line:
                continue
            field, separator, value = line.partition(":")
            if not separator:
                continue
            value = value.removeprefix(" ")
            if field == "event":
                kind = value
            elif field == "data":
                data.append(value)
        if data and kind == "message":
            messages.append(json.loads("\n".join(data)))
    if len(messages) != 1:
        raise ValueError("RPC_MESSAGE_COUNT")
    value = messages[0]
    if (
        type(value) is not dict
        or value.get("jsonrpc") != "2.0"
        or type(value.get("id")) is not type(expected_id)
        or value.get("id") != expected_id
        or set(value) != {"jsonrpc", "id", "result"}
        or type(value["result"]) is not dict
    ):
        raise ValueError("RPC_RESULT_INVALID")
    return value["result"]


def check_url(url):
    parsed = urlsplit(url)
    local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if (
        parsed.scheme != ("http" if local else "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path != "/mcp"
    ):
        raise ValueError("Use loopback HTTP or approved HTTPS /mcp without credentials/query")
    return local


def probe_endpoint(client, url, bearer):
    check_url(url)
    if len(bearer) != 64 or any(c not in "0123456789abcdef" for c in bearer):
        raise ValueError("Invalid private MCP credential")
    records = []

    def request(name, packet, credential=None, *, expected_status=200, version=None):
        headers = {"Accept": "application/json, text/event-stream"}
        if credential is not None:
            headers["Authorization"] = "Bearer " + credential
        if version is not None:
            headers["MCP-Protocol-Version"] = version
        started = time.perf_counter()
        row = {"check": name, "rpc_method": packet["method"], "status": "FAIL"}
        records.append(row)
        try:
            with client.stream("POST", url, headers=headers, json=packet) as response:
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise ValueError("RESPONSE_LIMIT")
                media = response.headers.get("content-type", "").split(";", 1)[0]
                row.update(
                    http_status=response.status_code,
                    content_type=media
                    if media in {"text/event-stream", "application/json"}
                    else "other",
                    auth_outcome="DENIED" if response.status_code == 401 else "UNVERIFIED",
                )
                if response.status_code != expected_status:
                    raise ValueError("HTTP_STATUS")
                if expected_status != 200:
                    row["status"] = "PASS"
                    return None
                if media != "text/event-stream":
                    raise ValueError("CONTENT_TYPE")
                value = parse_sse(body.decode("utf-8"), packet["id"])
                row.update(status="PASS", auth_outcome="ALLOWED", response_id_matches=True)
                return value
        except Exception as exc:
            row["error"] = safe_failure(exc)
            return None
        finally:
            row["request_elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)

    init = {
        "jsonrpc": "2.0",
        "id": "diagnostic-initialize",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "aegis-readonly-diagnostic", "version": "0.1.0"},
        },
    }
    request("missing_auth", init, expected_status=401)
    request("wrong_bearer", init, "0" * 64 if bearer != "0" * 64 else "1" * 64, expected_status=401)
    initialized = request("initialize", init, bearer)
    if initialized is None or initialized.get("protocolVersion") != "2025-06-18":
        records[-1]["status"] = "FAIL"
    request(
        "initialized_notification",
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        bearer,
        expected_status=202,
        version="2025-06-18",
    )
    result = request(
        "tools_list",
        {"jsonrpc": "2.0", "id": 22, "method": "tools/list"},
        bearer,
        version="2025-06-18",
    )
    count, valid = None, False
    if result is not None:
        try:
            tools = result["tools"]
            if type(tools) is not list or len(tools) > 16:
                raise ValueError("TOOL_LIST_INVALID")
            count = len(tools)
            for tool in tools:
                if type(tool) is not dict or tool.get("name") not in EXPECTED_TOOLS:
                    raise ValueError("UNEXPECTED_TOOL")
                Draft202012Validator.check_schema(tool["inputSchema"])
                if tool["inputSchema"].get("type") != "object":
                    raise ValueError("TOOL_SCHEMA_INVALID")
            valid = count == 2 and {tool["name"] for tool in tools} == EXPECTED_TOOLS
        except Exception:
            valid = False
        records[-1].update(tool_count=count, schemas_valid=valid)
        if not valid:
            records[-1]["status"] = "FAIL"
    return {
        "status": "PASS" if valid and all(row["status"] == "PASS" for row in records) else "FAIL",
        "tool_count": count,
        "requests": records,
    }


def safe_uuid(value):
    try:
        return str(UUID(value)) if type(value) is str else None
    except ValueError:
        return None


def cloud_inventory(directory):
    """Fresh supported SDK reads only. Dashboard-only fields remain UNVERIFIED."""
    client, email = build_client(directory)
    requests = []

    def started(request):
        request.extensions["aegis_inventory_started"] = time.perf_counter()

    client.http_client.event_hooks["request"].append(started)
    client.http_client.event_hooks["response"].append(
        lambda response: requests.append(
            {
                "http_status": response.status_code,
                "response_headers_ms": round(
                    (time.perf_counter() - response.request.extensions["aegis_inventory_started"])
                    * 1000,
                    3,
                ),
                "content_type": "application/json"
                if response.headers.get("content-type", "").startswith("application/json")
                else "other",
            }
        )
    )
    try:
        started = time.perf_counter()
        bootstrap = client.refresh_bootstrap()
        servers = client.list_mcps()
        tools = client.get_mcp_tool_schemas(MCP_NAME)
        context = client.resolve_user(email)
        policies = []
        for policy in context.get("policies", []):
            if policy.get("policyName") != "cli-aegis-relay-aegis-relay-mcp":
                continue
            rules = policy.get("rules", {})
            policies.append(
                {
                    "policy_id": safe_uuid(policy.get("policyId")),
                    "target_type": "mcp_server"
                    if policy.get("targetType") == "mcp_server"
                    else "other",
                    "target_id": safe_uuid(policy.get("targetId")),
                    "priority": policy.get("priority")
                    if type(policy.get("priority")) is int
                    else None,
                    "allowed_tools": [
                        tool for tool in rules.get("allowedTools", []) if tool in EXPECTED_TOOLS
                    ],
                    "denied_tools": [
                        tool for tool in rules.get("deniedTools", []) if tool in EXPECTED_TOOLS
                    ],
                    "default_action": policy.get("defaultEnforcementAction")
                    if policy.get("defaultEnforcementAction") in {"block", "allow", "deny", "hold"}
                    else None,
                    "enabled": policy.get("enabled")
                    if type(policy.get("enabled")) is bool
                    else None,
                    "active_status": "UNVERIFIED",
                }
            )
        registered = [server for server in servers if server.get("name") == MCP_NAME]
        endpoint_kind = []
        for server in registered:
            host = urlsplit(server.get("url", "")).hostname or ""
            endpoint_kind.append(
                "retired_quick_tunnel"
                if host.endswith(".trycloudflare.com")
                else "OTHER_UNVERIFIED"
            )
        return {
            "read_status": "PASS",
            "fresh_bootstrap": True,
            "org_id": safe_uuid(
                (bootstrap.get("org") or {}).get("orgId") or (bootstrap.get("org") or {}).get("id")
            ),
            "agent_ids": [
                safe_uuid(agent.get("agentId"))
                for agent in bootstrap.get("agents", [])
                if agent.get("name") == AGENT_NAME
            ],
            "mcp_ids": [safe_uuid(server.get("mcpId")) for server in registered],
            "endpoint_kind": endpoint_kind,
            "bootstrap_tool_count": sum(
                len(server.get("tools", []))
                for server in bootstrap.get("mcps", [])
                if server.get("name") == MCP_NAME
            ),
            "tool_schema_count": len(tools),
            "tool_map_count": len(bootstrap.get("toolMap", {})),
            "registered_auth_method": "UNVERIFIED",
            "policies": policies,
            "requests": requests,
            "inventory_elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "side_effect_calls": 0,
        }
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True, help="Reads only armoriq/mcp.bearer")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--external", action="store_true", help="Probe an operator-approved HTTPS endpoint"
    )
    parser.add_argument("--cli", action="store_true", help="Also use installed CLI discovery")
    parser.add_argument("--cloud", action="store_true", help="Opt-in fresh SDK inventory reads")
    args = parser.parse_args()
    if not check_url(args.url) and not args.external:
        raise ValueError("External probes require --external")
    if args.cloud and os.getenv("SAFEOPS_ARMORIQ_READONLY") != "1":
        raise ValueError("Cloud reads require SAFEOPS_ARMORIQ_READONLY=1")
    directory = args.state / "armoriq"
    bearer = (directory / "mcp.bearer").read_text("ascii")
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "network_level": "LOOPBACK" if check_url(args.url) else "EXTERNAL_HTTPS",
    }
    with httpx.Client(timeout=8, follow_redirects=False, verify=True, trust_env=False) as client:
        report["protocol"] = probe_endpoint(client, args.url, bearer)
    if args.cli:
        discovery = discover_mcp_tools(
            MCPServerConfig(id=MCP_NAME, url=args.url, auth={"type": "bearer", "token": bearer})
        )
        report["installed_cli_discovery"] = {
            "status": "PASS"
            if discovery.reachable
            and len(discovery.tools) == 2
            and set(discovery.tools) == EXPECTED_TOOLS
            else "FAIL",
            "tool_count": len(discovery.tools),
        }
    if args.cloud:
        # Installed SDK logging can contain provider bodies. Discard it, never save it.
        logging.disable(logging.CRITICAL)
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            try:
                report["armoriq_cloud"] = cloud_inventory(directory)
            except Exception as exc:
                report["armoriq_cloud"] = {"read_status": "FAIL", "error": safe_failure(exc)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
