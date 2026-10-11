"""Read-only platform check and isolated CLI validate/dry-run, never registration."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from armoriq_sdk.config import load_armoriq_config, save_armoriq_config

from safeops.integration.dispatch_permit import live_directory, load_store
from safeops.integration.live_armoriq import build_client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--mcp-url", default="http://127.0.0.1:8766/mcp")
    args = parser.parse_args()
    url = urlsplit(args.mcp_url)
    if (
        url.username
        or url.password
        or url.query
        or url.fragment
        or url.path != "/mcp"
        or (
            url.scheme != "https"
            and not (url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"})
        )
    ):
        raise ValueError("Use the separate authenticated MCP endpoint")
    store = load_store(args.state)
    directory = live_directory(args.state, store)
    client, email = build_client(directory)
    config = load_armoriq_config("armoriq.yaml")
    config.identity.user_id = email
    config.mcp_servers[0].url = args.mcp_url
    private_config = directory / "registration-review.yaml"
    save_armoriq_config(config, private_config)
    result = {
        "sdk": "0.6.10",
        "config_syntax": "PASS",
        "registration": "NOT_RUN",
        "policy_assignment": "NOT_RUN",
        "public_exposure": "NOT_STARTED",
        "review_config": str(private_config.resolve()),
    }
    try:
        data = client.bootstrap()
        result["auth"] = "PASS"
        # Counts are read-only observations, not proof of assignment or live enforcement.
        result["registered_agent_count"] = len(data.get("agents", []))
        result["registered_mcp_count"] = len(data.get("mcps", []))
    except Exception as exc:
        result.update(auth="BLOCKED", auth_error_class=type(exc).__name__)
    profile = directory / ("cli-dry-run-" + str(uuid4()))
    profile.mkdir(exist_ok=False, mode=0o700)
    env = os.environ.copy()
    env["USERPROFILE"] = str(profile.resolve())
    env["ARMORIQ_API_KEY"] = client.api_key
    env["SAFEOPS_MCP_BEARER"] = (directory / "mcp.bearer").read_text("ascii")
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        for command in ["validate", "register"]:
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "armoriq_sdk.cli",
                    command,
                    "--config",
                    str(private_config.resolve()),
                    *(["--dry-run"] if command == "register" else []),
                ],
                env=env,
                capture_output=True,
                timeout=35,
            )
            result["cli_validate" if command == "validate" else "cli_dry_run"] = (
                "PASS" if process.returncode == 0 else "BLOCKED"
            )
            # Do not publish CLI output: dry-run prints misleading registration claims.
    finally:
        client.close()
    (directory / "preflight.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
