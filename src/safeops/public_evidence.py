"""Strict sanitizer for read-only public display of persisted Azure evidence."""

import json
from datetime import UTC, datetime
from pathlib import Path

EXPECTED = {
    "run_id": "2d488ffa-9623-4501-9d2c-835ac5aa9dc0",
    "action_id": "fb689b14-75b8-4c78-b485-c61bac4c68a7",
    "plan_id": "d4e6d6a6-a077-4845-a81a-f61fa8129353",
    "policy_id": "c4b4d803-aefd-4c74-bc0c-dbb4564d399c",
    "policy_name": "cli-aegis-relay-aegis-relay-mcp",
    "enforcement_request_id": "42b8ce97-0643-4728-b21b-41ac701209df",
    "audit_id": "dc95ee03-ff15-4850-a774-c3bce756555b",
    "receipt_reference": "abc040ef-5664-45a1-bf9d-0d9e37cd6cfd",
    "effect_key": "b8feb3d7-7234-4cbb-a747-aaecba720529",
    "incident_id": "INC-261017",
}

HISTORICAL_DENIAL = {
    "status": "BLOCKED",
    "origin": "Real ArmorIQ production SDK-only feasibility check, Phase 2.2",
    "date_utc": "2026-10-11",
    "operation": "purge_incident_history",
    "reason": "tool_not_in_allowlist",
    "policy_id": EXPECTED["policy_id"],
    "request_id": "a1d37130-5f82-4e91-a752-6f58c9172f59",
    "source": (
        "https://github.com/miku-wwl/aig-flow-state/blob/main/"
        "docs/phase22-sdk-only-feasibility.md"
    ),
}

_TOP_LEVEL = {
    "schema_version",
    "status",
    "source",
    "run_id",
    "run_state",
    "run_version",
    "action_id",
    "action_state",
    "action_version",
    "plan_id",
    "tool_name",
    "tool_version",
    "target",
    "risk_class",
    "incident_id",
    "execution_path",
    "transport",
    "decision",
    "enforcement_http_status",
    "policy_id",
    "policy_name",
    "enforcement_request_id",
    "effect_count",
    "receipt_matched",
    "receipt_reference",
    "audit_status",
    "audit_id",
    "audit_http_status",
    "completion_http_status",
    "completion_success",
    "run_created_at_utc",
    "action_created_at_utc",
    "action_updated_at_utc",
    "execution_at_utc",
    "effect_created_at_utc",
}


class EvidenceMismatch(ValueError):
    """Persisted values do not prove the exact approved historical execution."""


def _require(condition):
    if not condition:
        raise EvidenceMismatch("Persisted evidence did not match the expected execution.")


def _timestamp(value):
    _require(type(value) is str and len(value) <= 64)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceMismatch("Persisted timestamp is invalid.") from exc
    _require(parsed.tzinfo is not None)
    return parsed.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _one(items, predicate):
    matches = [item for item in items if predicate(item)]
    _require(len(matches) == 1)
    return matches[0]


def build_public_evidence(run, action, records, policy_evidence, stage):
    """Validate backend readbacks, then return a narrow credential-free record."""
    _require(type(run) is dict and type(action) is dict and type(stage) is dict)
    _require(type(records) is list and type(policy_evidence) is dict)
    plan = run.get("plan")
    _require(
        run.get("run_id") == EXPECTED["run_id"]
        and run.get("state") == "Approved"
        and type(run.get("version")) is int
        and run["version"] == 5
        and run.get("risk_class") == "SIDE_EFFECT"
        and type(plan) is dict
        and plan.get("target") == "incident-desk"
        and plan.get("risk_class") == "SIDE_EFFECT"
        and type(plan.get("steps")) is list
        and len(plan["steps"]) == 1
    )
    step = plan["steps"][0]
    args = step.get("arguments") if type(step) is dict else None
    _require(
        type(args) is dict
        and args.get("incident_id") == EXPECTED["incident_id"]
        and step.get("tool_name") == "create_incident_handoff"
        and step.get("tool_version") == "1"
        and stage.get("plan_id") == EXPECTED["plan_id"]
        and stage.get("status") == "TERMINAL_OR_EXECUTING"
    )

    receipt = EXPECTED["receipt_reference"]
    _require(
        action.get("run_id") == EXPECTED["run_id"]
        and action.get("action_id") == EXPECTED["action_id"]
        and action.get("state") == "Succeeded"
        and type(action.get("version")) is int
        and action["version"] == 4
        and action.get("tool_name") == "create_incident_handoff"
        and action.get("tool_version") == "1"
        and action.get("target") == "incident-desk"
        and action.get("risk_class") == "SIDE_EFFECT"
        and type(action.get("result")) is dict
        and action["result"].get("receipt_reference") == receipt
    )

    _require(policy_evidence.get("mode") == "LIVE" and type(policy_evidence.get("events")) is list)
    events = policy_evidence["events"]
    action_id, plan_id = EXPECTED["action_id"], EXPECTED["plan_id"]
    succeeded = _one(
        events,
        lambda event: type(event) is dict
        and event.get("action_id") == action_id
        and event.get("status") == "SDK_SUCCEEDED",
    )
    acknowledged = _one(
        events,
        lambda event: type(event) is dict
        and event.get("action_id") == action_id
        and event.get("status") == "SDK_AUDIT_POST_ACKNOWLEDGED",
    )
    _require(
        succeeded.get("mode") == "LIVE"
        and succeeded.get("operation") == "create_incident_handoff"
        and succeeded.get("plan_id") == plan_id
        and succeeded.get("receipt_reference") == receipt
        and succeeded.get("effect_key") == EXPECTED["effect_key"]
        and acknowledged.get("mode") == "LIVE"
        and acknowledged.get("plan_id") == plan_id
        and acknowledged.get("receipt_reference") == receipt
        and acknowledged.get("effect_key") == EXPECTED["effect_key"]
    )
    diagnostics = succeeded.get("diagnostics")
    _require(
        type(diagnostics) is dict
        and diagnostics.get("path") == "sdk-only"
        and diagnostics.get("transport") == "REAL_PLATFORM"
        and type(diagnostics.get("execution")) is dict
        and diagnostics["execution"].get("explicit_remote_allow") is True
        and diagnostics["execution"].get("durable_record_verified") is True
    )
    enforcement = _one(
        diagnostics.get("http_events", []),
        lambda event: type(event) is dict and event.get("path") == "/iap/sdk/enforce",
    )
    _require(
        enforcement.get("http_status") == 200
        and enforcement.get("allowed") is True
        and enforcement.get("action") == "allow"
        and enforcement.get("policy_id") == EXPECTED["policy_id"]
        and enforcement.get("policy_name") == EXPECTED["policy_name"]
        and enforcement.get("server_request_id") == EXPECTED["enforcement_request_id"]
    )

    audit_http = acknowledged.get("diagnostics", {}).get("http_events", [])
    audit_report = _one(
        audit_http,
        lambda event: type(event) is dict and event.get("path") == "/iap/audit",
    )
    completion = _one(
        audit_http,
        lambda event: type(event) is dict
        and event.get("path") == f"/iap/plans/{plan_id}/status",
    )
    _require(
        audit_report.get("http_status") == 200
        and audit_report.get("plan_id") == plan_id
        and audit_report.get("audit_id") == EXPECTED["audit_id"]
        and completion.get("http_status") == 200
        and completion.get("plan_id") == plan_id
        and completion.get("success") is True
    )
    policy = stage.get("policy")
    _require(
        type(policy) is dict
        and policy.get("transport") == "REAL_PLATFORM"
        and policy.get("action") == "allow"
        and policy.get("explicit_allow_confirmed") is True
        and policy.get("policy_id") == EXPECTED["policy_id"]
        and policy.get("policy_name") == EXPECTED["policy_name"]
        and policy.get("server_request_id") == EXPECTED["enforcement_request_id"]
    )

    _require(len(records) == 1 and type(records[0]) is dict)
    record = records[0]
    _require(
        record.get("effect_key") == EXPECTED["effect_key"]
        and record.get("receipt_reference") == receipt
        and record.get("incident_id") == EXPECTED["incident_id"]
        and record.get("payload_digest") == diagnostics["execution"].get("payload_digest")
        and diagnostics["execution"].get("receipt_reference") == receipt
    )

    return {
        "schema_version": 1,
        "status": "VERIFIED",
        "source": "persisted VM-local Azure SDK-only runtime readback",
        "run_id": EXPECTED["run_id"],
        "run_state": run["state"],
        "run_version": run["version"],
        "action_id": EXPECTED["action_id"],
        "action_state": action["state"],
        "action_version": action["version"],
        "plan_id": plan_id,
        "tool_name": "create_incident_handoff",
        "tool_version": "1",
        "target": "incident-desk",
        "risk_class": "SIDE_EFFECT",
        "incident_id": EXPECTED["incident_id"],
        "execution_path": "SDK-only",
        "transport": "REAL_PLATFORM",
        "decision": "Allow",
        "enforcement_http_status": 200,
        "policy_id": EXPECTED["policy_id"],
        "policy_name": EXPECTED["policy_name"],
        "enforcement_request_id": EXPECTED["enforcement_request_id"],
        "effect_count": 1,
        "receipt_matched": True,
        "receipt_reference": receipt,
        "audit_status": "ACKNOWLEDGED",
        "audit_id": EXPECTED["audit_id"],
        "audit_http_status": 200,
        "completion_http_status": 200,
        "completion_success": True,
        "run_created_at_utc": _timestamp(run.get("created_at")),
        "action_created_at_utc": _timestamp(action.get("created_at")),
        "action_updated_at_utc": _timestamp(action.get("updated_at")),
        "execution_at_utc": _timestamp(succeeded.get("created_at")),
        "effect_created_at_utc": _timestamp(record.get("created_at")),
    }


def validate_public_evidence(data):
    """Reject missing, stale, inconsistent, or over-broad public evidence files."""
    if type(data) is not dict or set(data) != _TOP_LEVEL:
        return False
    expected_values = {
        "schema_version": 1,
        "status": "VERIFIED",
        "source": "persisted VM-local Azure SDK-only runtime readback",
        "run_id": EXPECTED["run_id"],
        "run_state": "Approved",
        "run_version": 5,
        "action_id": EXPECTED["action_id"],
        "action_state": "Succeeded",
        "action_version": 4,
        "plan_id": EXPECTED["plan_id"],
        "tool_name": "create_incident_handoff",
        "tool_version": "1",
        "target": "incident-desk",
        "risk_class": "SIDE_EFFECT",
        "incident_id": EXPECTED["incident_id"],
        "execution_path": "SDK-only",
        "transport": "REAL_PLATFORM",
        "decision": "Allow",
        "enforcement_http_status": 200,
        "policy_id": EXPECTED["policy_id"],
        "policy_name": EXPECTED["policy_name"],
        "enforcement_request_id": EXPECTED["enforcement_request_id"],
        "effect_count": 1,
        "receipt_matched": True,
        "receipt_reference": EXPECTED["receipt_reference"],
        "audit_status": "ACKNOWLEDGED",
        "audit_id": EXPECTED["audit_id"],
        "audit_http_status": 200,
        "completion_http_status": 200,
        "completion_success": True,
    }
    if any(
        type(data.get(key)) is not type(value) or data.get(key) != value
        for key, value in expected_values.items()
    ):
        return False
    try:
        for key in (
            "run_created_at_utc",
            "action_created_at_utc",
            "action_updated_at_utc",
            "execution_at_utc",
            "effect_created_at_utc",
        ):
            _timestamp(data.get(key))
    except EvidenceMismatch:
        return False
    return True


def public_evidence_payload(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        data = None
    verified = data if validate_public_evidence(data) else None
    return {
        "status": "VERIFIED" if verified else "UNVERIFIED",
        "current_execution_mode": "MOCK",
        "evidence": verified,
        "historical_denial": HISTORICAL_DENIAL,
    }
