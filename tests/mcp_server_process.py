"""Test-only subprocess shutdown channel, no operator UI."""

import argparse
import sys
import threading
from pathlib import Path

import uvicorn

from safeops.mcp.server import create_mcp_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--diagnostics", action="store_true")
    args = parser.parse_args()
    server = uvicorn.Server(
        uvicorn.Config(
            create_mcp_app(args.state, diagnostics=args.diagnostics),
            host="127.0.0.1",
            port=args.port,
            access_log=False,
        )
    )

    def stop():
        sys.stdin.readline()
        server.should_exit = True

    threading.Thread(target=stop, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
