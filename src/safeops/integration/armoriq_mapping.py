"""Execution-time mapping of reviewed inputs, never a second planner."""

from safeops.domain.handoff import valid_arguments

MCP_NAME = "aegis-relay-mcp"
AGENT_NAME = "aegis-relay"
CANARY = "purge_incident_history"


def captured_step(spec, binding, permit):
    if not binding.matches(spec) or not valid_arguments(dict(spec.arguments)):
        raise ValueError("Trusted binding mismatch")
    params = dict(spec.arguments) | {"_dispatch": permit}
    return {"steps": [{"mcp": MCP_NAME, "action": binding.tool_name, "params": params}]}, params


def receipt_payload(result):
    """Accept the documented MCP text result; never infer success from HTTP status."""
    import json

    if result.status != "success" or not isinstance(result.result, dict):
        raise ValueError("Missing MCP result")
    data = result.result
    if data.get("isError") or set(data) - {"content", "isError", "structuredContent"}:
        raise ValueError("Invalid MCP result")
    content = data.get("content")
    if not isinstance(content, list) or len(content) != 1:
        raise ValueError("Missing single receipt")
    item = content[0]
    if not isinstance(item, dict) or item.get("type") != "text":
        raise ValueError("Missing receipt text")
    return json.loads(item["text"])
