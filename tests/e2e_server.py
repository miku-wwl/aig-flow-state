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
    args = parser.parse_args()
    app = create_app(
        Settings(
            state=args.state,
            provider=args.provider,
            fixture_fault=args.fixture_fault,
            executor_fault=args.executor_fault,
            predecessor_stopped=True,
        )
    )
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, access_log=False))

    def stop_on_input():
        sys.stdin.readline()
        server.should_exit = True

    threading.Thread(target=stop_on_input, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
