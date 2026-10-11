"""Consumer dispatch integrity; the core remains the only Action authority."""

import base64
import json
import secrets
import time
from pathlib import Path
from uuid import UUID

from agentic_intent_gate.runtime import EXTERNAL_PAYLOAD_REVISION, ExecutionSpec, ToolBinding
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from safeops.domain.handoff import valid_arguments
from safeops.execution.handoff_store import HandoffStore

SERVICE = "aegis-relay-mcp"
FIELDS = {
    "version",
    "service",
    "action_id",
    "run_id",
    "authorization_id",
    "attempt_id",
    "effect_key",
    "payload_digest",
    "binding",
    "store_id",
    "issued_at",
    "expires_at",
}


class PermitRejected(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def uuid(value):
    if type(value) is not str or str(UUID(value, version=4)) != value:
        raise PermitRejected("Invalid dispatch identifier")
    return value


def load_store(state):
    state = Path(state).resolve()
    identity = json.loads((state / "identity.json").read_text("utf-8"))
    from safeops.domain.handoff import binding_for

    binding = ToolBinding(**identity["binding"])
    if binding != binding_for(binding.execution_scope):
        raise PermitRejected("Unexpected business binding")
    store = HandoffStore(state / "effects.sqlite3", binding, identity["store_id"])
    store.validate()
    return store


def provision_live(state):
    """Explicit, exclusive adjunct provisioning; never reset or migrate business data."""
    from safeops.integration.live_audit import LiveAudit
    from safeops.integration.runtime_composition import private_directory

    store = load_store(state)
    directory = Path(state).resolve() / "armoriq"
    private_directory(directory)
    key = Ed25519PrivateKey.generate()
    for name, value in [
        ("dispatch.key", key.private_bytes_raw()),
        ("dispatch.pub", key.public_key().public_bytes_raw()),
        ("mcp.bearer", secrets.token_hex(32).encode("ascii")),
    ]:
        with (directory / name).open("xb") as stream:
            stream.write(value)
        (directory / name).chmod(0o600)
    with (directory / "identity.json").open("x", encoding="utf-8") as stream:
        json.dump(
            {"service": SERVICE, "binding": vars(store.binding), "store_id": store.store_id},
            stream,
            indent=2,
        )
    LiveAudit.provision(directory / "audit.sqlite3")


def live_directory(state, store):
    directory = Path(state).resolve() / "armoriq"
    identity = json.loads((directory / "identity.json").read_text("utf-8"))
    if identity != {"service": SERVICE, "binding": vars(store.binding), "store_id": store.store_id}:
        raise PermitRejected("Live service identity mismatch")
    return directory


class PermitIssuer:
    def __init__(self, directory, store):
        self.key = Ed25519PrivateKey.from_private_bytes((directory / "dispatch.key").read_bytes())
        self.store = store
        self.runtime = None
        self.hints = {}

    def track(self, action_id):
        action = self.runtime.actions.get(action_id)
        if action is not None:
            self.hints[action.effect_key] = action.action_id

    def issue(self, spec, effect_key, context):
        action_id = self.hints.pop(effect_key, None)
        if action_id is None or self.runtime is None or context.expired():
            raise PermitRejected("No trusted claimed Action")
        action = self.runtime.actions.get(action_id)
        if (
            action is None
            or action.state.value != "Executing"
            or not action.authorization
            or action.effect_key != effect_key
            or ExecutionSpec.from_compiled(action.spec) != spec
        ):
            raise PermitRejected("Dispatch does not match authorized durable Action")
        import asyncio

        remaining = context.deadline - asyncio.get_running_loop().time()
        now = time.time()
        body = {
            "version": 1,
            "service": SERVICE,
            "action_id": uuid(action_id),
            "run_id": uuid(action.spec.run_id),
            "authorization_id": uuid(action.authorization["authorization_id"]),
            "attempt_id": uuid(context.attempt_id),
            "effect_key": uuid(effect_key),
            "payload_digest": spec.payload_digest(),
            "binding": vars(self.store.binding),
            "store_id": self.store.store_id,
            "issued_at": now,
            "expires_at": now + min(4, remaining - 0.25),
        }
        if body["expires_at"] <= now:
            raise PermitRejected("Dispatch budget exhausted")
        return {
            "body": body,
            "signature": base64.b64encode(self.key.sign(canonical(body))).decode("ascii"),
        }


class PermitVerifier:
    def __init__(self, directory, store):
        self.key = Ed25519PublicKey.from_public_bytes((directory / "dispatch.pub").read_bytes())
        self.store = store

    def verify(self, arguments):
        if type(arguments) is not dict or set(arguments) != {
            "incident_id",
            "summary",
            "handoff_note",
            "_dispatch",
        }:
            raise PermitRejected("Closed dispatch arguments required")
        args = {k: v for k, v in arguments.items() if k != "_dispatch"}
        if not valid_arguments(args):
            raise PermitRejected("Invalid business arguments")
        envelope = arguments["_dispatch"]
        if type(envelope) is not dict or set(envelope) != {"body", "signature"}:
            raise PermitRejected("Missing signed dispatch")
        body = envelope["body"]
        if type(body) is not dict or set(body) != FIELDS:
            raise PermitRejected("Invalid dispatch fields")
        try:
            self.key.verify(base64.b64decode(envelope["signature"], validate=True), canonical(body))
            for field in ["action_id", "run_id", "authorization_id", "attempt_id", "effect_key"]:
                uuid(body[field])
            now = time.time()
            if (
                type(body["issued_at"]) not in {float, int}
                or type(body["expires_at"]) not in {float, int}
                or not now - 5 <= body["issued_at"] <= now + 0.25
                or not now < body["expires_at"] <= body["issued_at"] + 4
                or body["version"] != 1
                or body["service"] != SERVICE
                or body["binding"] != vars(self.store.binding)
                or body["store_id"] != self.store.store_id
            ):
                raise PermitRejected("Expired or incorrectly bound dispatch")
            b = self.store.binding
            spec = ExecutionSpec(
                b.tool_name,
                b.tool_version,
                b.target,
                args,
                b.adapter_id,
                b.binding_revision,
                b.execution_scope,
                EXTERNAL_PAYLOAD_REVISION,
            )
            if spec.payload_digest() != body["payload_digest"]:
                raise PermitRejected("Approved payload mismatch")
        except PermitRejected:
            raise
        except Exception:
            raise PermitRejected("Dispatch integrity rejected") from None
        return spec, body


class DispatchDeadline:
    def __init__(self, expires_at):
        self.expires_at = expires_at

    def expired(self):
        return time.time() >= self.expires_at
