import re

from agentic_intent_gate.runtime import ToolBinding, ToolCapability

ARGUMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["incident_id", "summary", "handoff_note"],
    "properties": {
        "incident_id": {
            "type": "string",
            "minLength": 5,
            "maxLength": 32,
            "pattern": r"^INC-[0-9]{1,12}$",
        },
        "summary": {"type": "string", "minLength": 1, "maxLength": 256, "pattern": r"\S"},
        "handoff_note": {"type": "string", "minLength": 1, "maxLength": 1024, "pattern": r"\S"},
    },
}


def binding_for(scope):
    return ToolBinding(
        "create_incident_handoff", "1", "safeops-armoriq", "safeops-v1", "incident-desk", scope
    )


def valid_arguments(args):
    return (
        set(args) == set(ARGUMENT_SCHEMA["required"])
        and all(
            type(args[name]) is str
            and field["minLength"] <= len(args[name]) <= field["maxLength"]
            and args[name].strip()
            and len(args[name].encode("utf-8")) <= field["maxLength"] * 4
            and not any(ord(c) < 32 and c not in "\t\n\r" for c in args[name])
            and "\x7f" not in args[name]
            for name, field in ARGUMENT_SCHEMA["properties"].items()
        )
        and re.fullmatch(r"INC-[0-9]{1,12}", args["incident_id"]) is not None
    )


def capability_for(binding):
    return ToolCapability(
        binding,
        "Create one reviewed synthetic incident handoff in the local incident desk",
        ARGUMENT_SCHEMA,
        semantic_rule=lambda args, target: None if valid_arguments(args) else "INPUT_REJECTED",
    )
