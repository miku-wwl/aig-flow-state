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
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_thinking: str = "disabled"

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
        if self.provider not in {"ollama", "fixture", "deepseek"}:
            raise ValueError("Choose ollama, fixture or deepseek explicitly")
        from safeops.planning.deepseek_provider import validate_deepseek_options

        validate_deepseek_options(
            self.deepseek_base_url, self.deepseek_model, self.deepseek_thinking
        )
        if self.enforcement_mode not in {"mock", "real", "proxy", "sdk-only"}:
            raise ValueError("Choose mock, proxy (legacy real) or sdk-only explicitly")
        if self.enforcement_mode != "mock" and self.executor_fault != "none":
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
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
            deepseek_thinking=os.getenv("DEEPSEEK_THINKING", "disabled"),
        )
