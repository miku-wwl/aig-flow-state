import csv
import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from agentic_intent_gate.runtime import (
    BoundCapabilityAuthorization,
    CapabilityVerifier,
    ExecutableRegistry,
    ToolBinding,
    open_runtime,
    provision_capability,
)

from safeops.configuration import Settings
from safeops.domain.handoff import binding_for, capability_for
from safeops.execution.handoff_executor import HandoffExecutor
from safeops.execution.handoff_store import HandoffStore
from safeops.integration.mock_armoriq import MockArmorIQClient
from safeops.planning.fixture_provider import DeterministicFixtureProvider
from safeops.planning.ollama_provider import OllamaSafeOpsProvider

MANIFEST_VERSION = 1
SUBJECT = "safeops-local-operator"
POLICY_REVISION = "safeops-policy-v1"


def private_directory(path):
    path.mkdir(parents=True, exist_ok=False, mode=0o700)
    if os.name == "nt":
        result = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            check=True,
        )
        sid = next(csv.reader(result.stdout.splitlines()))[1]
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"],
            capture_output=True,
            check=True,
        )


def provision(directory):
    directory = Path(directory).resolve()
    private_directory(directory)
    binding = binding_for(str(uuid4()))
    store_id = str(uuid4())
    provision_capability(directory / "capability")
    HandoffStore.provision(directory / "effects.sqlite3", binding, store_id)
    identity = {
        "manifest_version": MANIFEST_VERSION,
        "subject_id": SUBJECT,
        "policy_revision": POLICY_REVISION,
        "binding": vars(binding),
        "store_id": store_id,
    }
    with (directory / "identity.json").open("x", encoding="utf-8") as stream:
        json.dump(identity, stream, indent=2)
    # Explicit initialization also creates the core DB using only the public composition.
    with composition(
        Settings(state=directory, provider="fixture", predecessor_stopped=True), provision_gate=True
    ):
        pass


@contextmanager
def composition(settings, *, provider=None, enforcement=None, provision_gate=False):
    directory = settings.state.resolve()
    identity = json.loads((directory / "identity.json").read_text("utf-8"))
    if (
        set(identity)
        != {"manifest_version", "subject_id", "policy_revision", "binding", "store_id"}
        or identity["manifest_version"] != MANIFEST_VERSION
        or identity["subject_id"] != SUBJECT
        or identity["policy_revision"] != POLICY_REVISION
    ):
        raise ValueError("Unsupported trusted identity; no automatic provisioning or migration")
    binding = ToolBinding(**identity["binding"])
    if binding != binding_for(binding.execution_scope):
        raise ValueError("Trusted Aegis Relay binding mismatch")
    store = HandoffStore(directory / "effects.sqlite3", binding, identity["store_id"])
    store.validate()
    provider = provider or (
        DeterministicFixtureProvider(fault=settings.fixture_fault)
        if settings.provider == "fixture"
        else OllamaSafeOpsProvider(
            settings.ollama_url, model=settings.model, timeout=settings.model_timeout
        )
    )
    enforcement = enforcement or MockArmorIQClient(
        binding, allowed_tools=set() if settings.executor_fault == "policy_deny" else None
    )
    executor = HandoffExecutor(
        store, enforcement, lose_ack=settings.executor_fault == "post_commit_ack_loss"
    )
    verifier = CapabilityVerifier(
        (directory / "capability").read_text("ascii"),
        subject_id=identity["subject_id"],
        binding=binding,
        operations=("read", "admit", "authorize", "execute"),
    )
    policy = BoundCapabilityAuthorization(verifier, policy_revision=identity["policy_revision"])
    registry = ExecutableRegistry(executor, binding=binding)
    # All normal starts require the database initialized by `safeops init`.
    if not (directory / "gate.sqlite3").exists():
        if not provision_gate:
            raise ValueError("Missing gate DB; initialize a new private state directory explicitly")
    with open_runtime(
        gate_path=directory / "gate.sqlite3",
        provider=provider,
        capability=capability_for(binding),
        registry=registry,
        verifier=verifier,
        policy=policy,
        predecessor_stopped=settings.predecessor_stopped,
    ) as runtime:
        yield runtime, store, provider, enforcement, executor
