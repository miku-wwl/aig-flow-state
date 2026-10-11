import json
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from agentic_intent_gate.runtime import Intent

from safeops.configuration import Settings
from safeops.domain.handoff import binding_for, capability_for
from safeops.planning.fixture_provider import DeterministicFixtureProvider, fixture_plan
from safeops.planning.ollama_provider import OllamaSafeOpsProvider


@pytest.fixture
def validator():
    return capability_for(binding_for(str(uuid4()))).build_validator()


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_tool",
        "wrong_version",
        "wrong_target",
        "extra_plan_field",
        "extra_argument",
        "missing_argument",
        "wrong_type",
        "empty",
        "whitespace",
        "oversized",
        "invalid_incident",
        "multi_step",
        "wrong_risk",
        "model_binding",
        "control_character",
    ],
)
def test_strict_plan_rejection(validator, mutation):
    plan = deepcopy(fixture_plan("INC-1042"))
    step, args = plan["steps"][0], plan["steps"][0]["arguments"]
    match mutation:
        case "unknown_tool":
            step["tool_name"] = "purge_incident_history"
        case "wrong_version":
            step["tool_version"] = "2"
        case "wrong_target":
            plan["target"] = "production"
        case "extra_plan_field":
            plan["authorized"] = True
        case "extra_argument":
            args["command"] = "arbitrary"
        case "missing_argument":
            del args["summary"]
        case "wrong_type":
            args["summary"] = 42
        case "empty":
            args["summary"] = ""
        case "whitespace":
            args["handoff_note"] = "   "
        case "oversized":
            args["handoff_note"] = "x" * 1025
        case "invalid_incident":
            args["incident_id"] = "INC-bad"
        case "multi_step":
            plan["steps"].append(deepcopy(step))
        case "wrong_risk":
            plan["risk_class"] = "READ_ONLY"
        case "model_binding":
            step["adapter_id"] = "malicious"
        case "control_character":
            args["summary"] = "bad\x00value"
    with pytest.raises(Exception) as error:  # noqa: B017 - not exported by the runtime module
        validator.parse_plan(json.dumps(plan))
    assert type(error.value).__name__ == "ValidationFailure"


def test_duplicate_json_key_rejected(validator):
    raw = json.dumps(fixture_plan("INC-1042"))
    raw = raw.replace('"target": "incident-desk"', '"target":"production","target":"incident-desk"')
    with pytest.raises(Exception) as error:  # noqa: B017 - verify the concrete failure below
        validator.parse_plan(raw)
    assert type(error.value).__name__ == "ValidationFailure"


async def test_fixture_contract(validator):
    raw = await DeterministicFixtureProvider().generate_plan(Intent("Create handoff INC-12"))
    assert validator.parse_plan(raw).to_dict()["steps"][0]["arguments"]["incident_id"] == "INC-12"


@pytest.mark.parametrize(
    "endpoint", ["https://cloud.invalid", "http://remote.invalid", "http://user:password@localhost"]
)
def test_cloud_endpoint_rejected(endpoint):
    with pytest.raises(ValueError):
        Settings(ollama_url=endpoint)


async def test_ollama_request_contract(monkeypatch, validator):
    requests = []

    def transport(request):
        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "phi4-mini:latest"}]})
        body = json.loads(request.content)
        assert body["model"] == "phi4-mini:latest"
        assert body["response_format"]["type"] == "json_schema"
        assert body["messages"][1]["content"] == "INC-1042"
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(fixture_plan("INC-1042"))}}]}
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(transport), **kwargs),
    )
    provider = OllamaSafeOpsProvider("http://127.0.0.1:11434")
    raw = await provider.generate_plan(
        Intent("INC-1042"),
        tools=validator.tools,
        plan_schema=validator.plan_schema,
        timeout_seconds=28,
    )
    validator.parse_plan(raw)
    assert len(requests) == 2 and provider.responses == 1


async def test_missing_local_model_never_falls_back(monkeypatch, validator):
    original = httpx.AsyncClient
    mock = httpx.MockTransport(lambda request: httpx.Response(200, json={"models": []}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=mock, **kwargs))
    provider = OllamaSafeOpsProvider("http://127.0.0.1:11434")
    with pytest.raises(ConnectionError):
        await provider.generate_plan(
            Intent("INC-1042"),
            tools=validator.tools,
            plan_schema=validator.plan_schema,
            timeout_seconds=28,
        )
    assert provider.mode == "ollama" and provider.responses == 0
    assert provider.last_error == "LOCAL_PHI4_MINI_NOT_INSTALLED"
