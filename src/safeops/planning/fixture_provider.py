import json
import re


def fixture_plan(text):
    match = re.search(r"\bINC-[0-9]{1,12}\b", text)
    return {
        "goal": "Create a reviewed incident handoff",
        "target": "incident-desk",
        "steps": [
            {
                "tool_name": "create_incident_handoff",
                "tool_version": "1",
                "arguments": {
                    "incident_id": match.group() if match else "INC-1042",
                    "summary": "Checkout API errors require investigation",
                    "handoff_note": "Investigate the upstream dependency and preserve notes.",
                },
            }
        ],
        "risk_class": "SIDE_EFFECT",
    }


class DeterministicFixtureProvider:
    """Explicit test mode. Never selected after an Ollama failure."""

    mode = "fixture"

    def __init__(self, *, raw=None, fault="none"):
        self.raw, self.fault = raw, fault
        self.last_error = None
        self.calls = 0

    async def generate_plan(self, intent, **kwargs):
        self.calls += 1
        if self.fault == "timeout":
            self.last_error = "MODEL_TIMEOUT"
            raise TimeoutError("Deterministic provider timeout")
        if self.fault == "unavailable":
            self.last_error = "MODEL_UNAVAILABLE"
            raise ConnectionError("Deterministic unavailable provider")
        if self.fault == "invalid_json":
            self.last_error = "INVALID_JSON"
            return "{invalid JSON"
        return self.raw if self.raw is not None else json.dumps(fixture_plan(intent.text))

    def status(self):
        return {
            "mode": self.mode,
            "model": None,
            "calls": self.calls,
            "last_error": self.last_error,
        }
