import json
import socket
import subprocess
import sys
import time

import httpx
from armoriq_sdk.cli import discover_mcp_tools
from armoriq_sdk.config import MCPServerConfig

from safeops.integration.dispatch_permit import load_store, provision_live
from tests.test_live_armoriq import signed_params


def test_actual_network_mcp_cli_discovery_and_invocation(state):
    provision_live(state)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    bearer = (state / "armoriq" / "mcp.bearer").read_text("ascii")
    url = f"http://127.0.0.1:{port}/mcp"
    headers = {"Authorization": "Bearer " + bearer}
    with (state / "mcp.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tests.mcp_server_process",
                "--state",
                str(state),
                "--port",
                str(port),
            ],
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=log,
            text=True,
        )
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                assert process.poll() is None
                try:
                    response = httpx.post(
                        url,
                        headers=headers,
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "initialize",
                            "params": {"protocolVersion": "2024-11-05"},
                        },
                        timeout=1,
                        trust_env=False,
                    )
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    time.sleep(0.1)
            else:
                raise AssertionError("MCP startup did not complete")
            config = MCPServerConfig(
                id="aegis-relay-mcp", url=url, auth={"type": "bearer", "token": bearer}
            )
            discovery = discover_mcp_tools(config)
            assert discovery.reachable and set(discovery.tools) == {
                "create_incident_handoff",
                "purge_incident_history",
            }
            response = httpx.post(
                url,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "create_incident_handoff",
                        "arguments": signed_params(state),
                    },
                },
                timeout=3,
                trust_env=False,
            )
            result = json.loads(response.text.split("data: ")[1])["result"]
            receipt = json.loads(result["content"][0]["text"])
            assert (
                load_store(state).records()[0]["receipt_reference"] == receipt["receipt_reference"]
            )
        finally:
            process.stdin.write("stop\n")
            process.stdin.flush()
            process.wait(timeout=45)
            process.stdin.close()
            assert process.returncode == 0
