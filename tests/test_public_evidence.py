import copy
import json

import pytest

from safeops.public_evidence import (
    EvidenceMismatch,
    build_public_evidence,
    public_evidence_payload,
    validate_public_evidence,
)


def persisted_readback():
    run = {
        "run_id": "2d488ffa-9623-4501-9d2c-835ac5aa9dc0",
        "state": "Approved",
        "version": 5,
        "risk_class": "SIDE_EFFECT",
        "created_at": "2026-10-16T11:45:10.580630Z",
        "plan": {
            "target": "incident-desk",
            "risk_class": "SIDE_EFFECT",
            "steps": [
                {
                    "tool_name": "create_incident_handoff",
                    "tool_version": "1",
                    "arguments": {"incident_id": "INC-261017"},
                }
            ],
        },
    }
    action = {
        "run_id": run["run_id"],
        "action_id": "fb689b14-75b8-4c78-b485-c61bac4c68a7",
        "state": "Succeeded",
        "version": 4,
        "tool_name": "create_incident_handoff",
        "tool_version": "1",
        "target": "incident-desk",
        "risk_class": "SIDE_EFFECT",
        "created_at": "2026-10-16T12:18:05.813980Z",
        "updated_at": "2026-10-16T12:27:08.218471Z",
        "result": {"receipt_reference": "abc040ef-5664-45a1-bf9d-0d9e37cd6cfd"},
    }
    execution = {
        "action_id": action["action_id"],
        "status": "SDK_SUCCEEDED",
        "mode": "LIVE",
        "operation": "create_incident_handoff",
        "plan_id": "d4e6d6a6-a077-4845-a81a-f61fa8129353",
        "effect_key": "b8feb3d7-7234-4cbb-a747-aaecba720529",
        "receipt_reference": action["result"]["receipt_reference"],
        "created_at": "2026-10-16T12:27:08.248204+00:00",
        "diagnostics": {
            "path": "sdk-only",
            "transport": "REAL_PLATFORM",
            "execution": {
                "explicit_remote_allow": True,
                "durable_record_verified": True,
                "payload_digest": (
                    "4b542901ee5e30e67b579003a6ddb5ac65b24dacd7a9a1633a0be274dabbe543"
                ),
                "receipt_reference": action["result"]["receipt_reference"],
            },
            "http_events": [
                {
                    "path": "/iap/sdk/enforce",
                    "http_status": 200,
                    "allowed": True,
                    "action": "allow",
                    "policy_id": "c4b4d803-aefd-4c74-bc0c-dbb4564d399c",
                    "policy_name": "cli-aegis-relay-aegis-relay-mcp",
                    "server_request_id": "42b8ce97-0643-4728-b21b-41ac701209df",
                }
            ],
        },
    }
    acknowledged = {
        "action_id": action["action_id"],
        "status": "SDK_AUDIT_POST_ACKNOWLEDGED",
        "mode": "LIVE",
        "plan_id": "d4e6d6a6-a077-4845-a81a-f61fa8129353",
        "effect_key": "b8feb3d7-7234-4cbb-a747-aaecba720529",
        "receipt_reference": action["result"]["receipt_reference"],
        "diagnostics": {
            "http_events": [
                {
                    "path": "/iap/audit",
                    "http_status": 200,
                    "plan_id": "d4e6d6a6-a077-4845-a81a-f61fa8129353",
                    "audit_id": "dc95ee03-ff15-4850-a774-c3bce756555b",
                },
                {
                    "path": "/iap/plans/d4e6d6a6-a077-4845-a81a-f61fa8129353/status",
                    "http_status": 200,
                    "plan_id": "d4e6d6a6-a077-4845-a81a-f61fa8129353",
                    "success": True,
                },
            ]
        },
    }
    records = [
        {
            "effect_key": "b8feb3d7-7234-4cbb-a747-aaecba720529",
            "receipt_reference": action["result"]["receipt_reference"],
            "incident_id": "INC-261017",
            "payload_digest": execution["diagnostics"]["execution"]["payload_digest"],
            "created_at": "2026-10-16T12:27:08.192393+00:00",
        }
    ]
    policy = {
        "mode": "LIVE",
        "events": [execution, acknowledged],
    }
    stage = {
        "status": "TERMINAL_OR_EXECUTING",
        "plan_id": "d4e6d6a6-a077-4845-a81a-f61fa8129353",
        "policy": {
            "transport": "REAL_PLATFORM",
            "action": "allow",
            "explicit_allow_confirmed": True,
            "policy_id": "c4b4d803-aefd-4c74-bc0c-dbb4564d399c",
            "policy_name": "cli-aegis-relay-aegis-relay-mcp",
            "server_request_id": "42b8ce97-0643-4728-b21b-41ac701209df",
        },
    }
    return run, action, records, policy, stage


def test_persisted_allow_receipt_and_audit_are_sanitized():
    evidence = build_public_evidence(*persisted_readback())
    assert validate_public_evidence(evidence)
    assert evidence["decision"] == "Allow"
    assert evidence["receipt_matched"] is True and evidence["effect_count"] == 1
    assert evidence["audit_status"] == "ACKNOWLEDGED"
    assert "capability" not in json.dumps(evidence).lower()
    assert "diagnostics" not in evidence and "arguments" not in evidence


def test_non_allow_mismatch_or_duplicate_effect_fails_closed():
    run, action, records, policy, stage = persisted_readback()
    policy = copy.deepcopy(policy)
    policy["events"][0]["diagnostics"]["http_events"][0]["allowed"] = False
    with pytest.raises(EvidenceMismatch):
        build_public_evidence(run, action, records, policy, stage)

    run, action, records, policy, stage = persisted_readback()
    with pytest.raises(EvidenceMismatch):
        build_public_evidence(run, action, records * 2, policy, stage)


def test_public_file_is_unverified_when_missing_malformed_or_overbroad(tmp_path):
    path = tmp_path / "evidence.json"
    payload = public_evidence_payload(path)
    assert payload["status"] == "UNVERIFIED"
    assert payload["current_execution_mode"] == "MOCK"
    assert payload["evidence"] is None
    assert payload["historical_denial"]["status"] == "BLOCKED"

    evidence = build_public_evidence(*persisted_readback())
    evidence["private_capability"] = "must never be returned"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    payload = public_evidence_payload(path)
    assert payload["status"] == "UNVERIFIED"
    assert payload["evidence"] is None


def test_valid_file_returns_only_whitelisted_evidence(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(build_public_evidence(*persisted_readback())), encoding="utf-8")
    payload = public_evidence_payload(path)
    assert payload["status"] == "VERIFIED"
    assert payload["evidence"]["action_state"] == "Succeeded"
    assert payload["evidence"]["transport"] == "REAL_PLATFORM"
