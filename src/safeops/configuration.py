import math
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    state: Path = Path(".runtime/local")
    provider: str = "ollama"
    ollama_url: str = "http://127.0.0.1:11434"
    model: str | None = None
    model_timeout: float = 28
    fixture_fault: str = "none"
    executor_fault: str = "none"
    predecessor_stopped: bool = False
    enforcement_mode: str = "mock"

    def __post_init__(self):
        url = urlsplit(self.ollama_url)
        if (
            url.scheme != "http"
            or url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError("Ollama must use a local HTTP endpoint")
        if self.provider not in {"ollama", "fixture"}:
            raise ValueError("Choose ollama or fixture explicitly")
        if self.enforcement_mode not in {"mock", "real"}:
            raise ValueError("Choose mock or real enforcement explicitly")
        if self.enforcement_mode == "real" and self.executor_fault != "none":
            raise ValueError("Real enforcement does not accept mock execution faults")
        if not math.isfinite(self.model_timeout) or not 0 < self.model_timeout <= 28:
            raise ValueError("Model timeout must be in (0, 28], within the core HTTP budget")
        if self.fixture_fault not in {"none", "timeout", "invalid_json", "unavailable"}:
            raise ValueError("Unknown planning fixture fault")
        if self.executor_fault not in {"none", "post_commit_ack_loss", "policy_deny"}:
            raise ValueError("Unknown deterministic execution fault")
        if self.provider != "fixture" and (
            self.fixture_fault != "none" or self.executor_fault != "none"
        ):
            raise ValueError("Fault injection requires explicit fixture mode")

    @classmethod
    def from_env(cls, *, predecessor_stopped=False):
        return cls(
            state=Path(os.getenv("SAFEOPS_STATE", ".runtime/local")),
            provider=os.getenv("SAFEOPS_PROVIDER", "ollama"),
            ollama_url=os.getenv("SAFEOPS_OLLAMA_URL", "http://127.0.0.1:11434"),
            model=os.getenv("SAFEOPS_MODEL") or None,
            model_timeout=float(os.getenv("SAFEOPS_MODEL_TIMEOUT", "28")),
            predecessor_stopped=predecessor_stopped,
            enforcement_mode=os.getenv("SAFEOPS_ENFORCEMENT_MODE", "mock"),
        )
