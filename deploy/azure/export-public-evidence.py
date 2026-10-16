"""Export one strict, credential-free view of the persisted operator Action."""

import grp
import json
import os
import shutil
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from safeops.public_evidence import build_public_evidence

STATE = Path("/var/lib/aegis-relay-sdk-only/runtime")
OUTPUT = Path("/etc/aegis-relay-public/public-evidence.json")
BASE_URL = "http://localhost:8770"
RUN_ID = "2d488ffa-9623-4501-9d2c-835ac5aa9dc0"
ACTION_ID = "fb689b14-75b8-4c78-b485-c61bac4c68a7"


class RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


OPENER = build_opener(ProxyHandler({}), RejectRedirect())


def get_json(path, capability):
    request = Request(
        BASE_URL + path,
        headers={"Authorization": "Bearer " + capability, "Accept": "application/json"},
        method="GET",
    )
    try:
        with OPENER.open(request, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError
            body = response.read(64 * 1024 + 1)
            if len(body) > 64 * 1024:
                raise RuntimeError
            return json.loads(body)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("Persisted backend evidence could not be read safely.") from exc


def main():
    capability = (STATE / "capability").read_text(encoding="ascii").strip()
    run = get_json("/api/runs/" + RUN_ID, capability)
    action = get_json("/api/actions/" + ACTION_ID, capability)
    records = get_json("/api/handoffs", capability).get("records")
    policy_evidence = get_json("/api/policy/evidence", capability)
    stage = get_json("/api/actions/" + ACTION_ID + "/sdk-stage", capability)
    evidence = build_public_evidence(run, action, records, policy_evidence, stage)

    OUTPUT.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    group_id = grp.getgrnam("aegis-relay").gr_gid
    shutil.chown(OUTPUT.parent, user="root", group="aegis-relay")
    os.chmod(OUTPUT.parent, 0o750)
    fd, temporary = tempfile.mkstemp(prefix=".public-evidence-", dir=OUTPUT.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(evidence, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(temporary, 0, group_id)
        os.chmod(temporary, 0o640)
        os.replace(temporary, OUTPUT)
        directory = os.open(OUTPUT.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("PUBLIC_EVIDENCE=VERIFIED")
    print("SOURCE=persisted VM-local read-only API")
    print("NEW_ACTIONS=0")


if __name__ == "__main__":
    main()
