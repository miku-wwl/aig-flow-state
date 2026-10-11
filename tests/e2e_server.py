"""Real uvicorn process with a test-only stdin graceful-stop channel."""

import argparse
import sys
import threading
from pathlib import Path

import uvicorn

from safeops.configuration import Settings
from safeops.main import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--provider", default="fixture")
    parser.add_argument("--fixture-fault", default="none")
    parser.add_argument("--executor-fault", default="none")
    parser.add_argument(
        "--enforcement-mode", choices=["mock", "real", "proxy", "sdk-only"], default="mock"
    )
    parser.add_argument("--sdk-fault", default="none")
    parser.add_argument("--offline-sdk", action="store_true")
    args = parser.parse_args()
    enforcement = None
    if args.offline_sdk:
        if args.enforcement_mode == "sdk-only":
            from tests.test_sdk_application import offline_application

            enforcement, _ = offline_application(args.state, fault=args.sdk_fault)
        else:
            from tests.armoriq_harness import offline_live

            enforcement = offline_live(args.state, fault=args.sdk_fault).live
    app = create_app(
        Settings(
            state=args.state,
            provider=args.provider,
            fixture_fault=args.fixture_fault,
            executor_fault=args.executor_fault,
            predecessor_stopped=True,
            enforcement_mode=args.enforcement_mode,
        ),
        enforcement=enforcement,
    )
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, access_log=False))

    def stop_on_input():
        sys.stdin.readline()
        server.should_exit = True

    threading.Thread(target=stop_on_input, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
