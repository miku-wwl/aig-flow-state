import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx


class ServerHarness:
    def __init__(
        self,
        state,
        *,
        provider="fixture",
        fixture_fault="none",
        executor_fault="none",
        enforcement_mode="mock",
        sdk_fault="none",
        offline_sdk=False,
    ):
        self.state = Path(state)
        self.provider, self.fixture_fault, self.executor_fault = (
            provider,
            fixture_fault,
            executor_fault,
        )
        with socket.socket() as socket_:
            socket_.bind(("127.0.0.1", 0))
            self.port = socket_.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.process = None
        self.log = None
        self.enforcement_mode, self.sdk_fault, self.offline_sdk = (
            enforcement_mode,
            sdk_fault,
            offline_sdk,
        )

    def start(self):
        self.log = (self.state / "server.log").open("a", encoding="utf-8")
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tests.e2e_server",
                "--state",
                str(self.state),
                "--port",
                str(self.port),
                "--provider",
                self.provider,
                "--fixture-fault",
                self.fixture_fault,
                "--executor-fault",
                self.executor_fault,
                "--enforcement-mode",
                self.enforcement_mode,
                "--sdk-fault",
                self.sdk_fault,
                *(["--offline-sdk"] if self.offline_sdk else []),
            ],
            stdin=subprocess.PIPE,
            stdout=self.log,
            stderr=self.log,
            text=True,
            env=env,
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("Server startup failed; inspect sanitized server.log")
            try:
                response = httpx.get(self.url + "/api/health", timeout=1, trust_env=False)
                if response.status_code == 200:
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise TimeoutError("Server did not become healthy")

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.stdin.write("stop\n")
            self.process.stdin.flush()
            self.process.wait(timeout=45)
            assert self.process.returncode == 0, "Server did not stop gracefully"
        if self.process is not None:
            self.process.stdin.close()
        if self.log:
            self.log.close()

    @property
    def headers(self):
        return {"Authorization": "Bearer " + (self.state / "capability").read_text("ascii")}

    def get(self, path):
        response = httpx.get(self.url + path, headers=self.headers, timeout=10, trust_env=False)
        response.raise_for_status()
        return response.json()


def save_evidence(name, value):
    directory = artifact_directory("evidence")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (name + ".json")).write_text(json.dumps(value, indent=2), encoding="utf-8")


def artifact_directory(name):
    return Path(os.getenv("SAFEOPS_TEST_ARTIFACTS", ".artifacts")) / name
