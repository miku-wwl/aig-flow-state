"""Opt-in real platform/browser qualification; never deploy, register, or submit."""

import argparse
import json
import os
import re
import sqlite3
from pathlib import Path
from uuid import UUID

import httpx
from armoriq_sdk.cli import discover_mcp_tools
from armoriq_sdk.config import MCPServerConfig
from playwright.sync_api import expect, sync_playwright

from safeops.integration.dispatch_permit import live_directory, load_store
from safeops.integration.live_armoriq import build_client
from safeops.integration.live_audit import LiveAudit
from tests.server_harness import ServerHarness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume-run", type=UUID)
    parser.add_argument("--prior-denial", type=Path)
    args = parser.parse_args()
    if os.getenv("SAFEOPS_REAL_E2E") != "1":
        raise RuntimeError("Opt in with SAFEOPS_REAL_E2E=1 after exposure/registration approval")
    if not args.public_url.startswith("https://"):
        raise ValueError("Real qualification requires public HTTPS MCP reachability")
    store = load_store(args.state)
    directory = live_directory(args.state, store)
    if store.records():
        raise ValueError("Use the prepared empty release state; never reset existing business data")
    args.output.mkdir(parents=True, exist_ok=False)
    result = {
        "platform": "REAL",
        "PHASE2_REAL_E2E": "BLOCKED",
        "READY_TO_SUBMIT": "NO",
        "ACTUALLY_SUBMITTED": "NO",
        "registration": "UNVERIFIED",
        "policy_assignment": "UNVERIFIED",
        "dashboard_audit": "NOT_CAPTURED",
        "public_mcp_url": args.public_url,
    }
    client, _ = build_client(directory)
    server = ServerHarness(args.state, provider="ollama", enforcement_mode="real")
    run_id = None
    canary_attempted = False
    try:
        if args.prior_denial:
            prior = json.loads(args.prior_denial.read_text("utf-8"))
            denial = prior.get("denial", {})
            if (
                prior.get("platform") != "REAL"
                or not denial.get("policy_denial_verified")
                or not denial.get("effect_store_unchanged")
                or denial.get("event_id")
                not in {
                    event["event_id"] for event in LiveAudit(directory / "audit.sqlite3").events()
                }
            ):
                raise ValueError("Prior denial must match this prepared state's durable audit")
            canary_attempted = True
            result.update(denial=denial, policy_denial="PASS", no_forbidden_effect="PASS")
        client.bootstrap()
        result["auth"] = "PASS"
        discovery = discover_mcp_tools(
            MCPServerConfig(
                id="aegis-relay-mcp",
                url=args.public_url,
                auth={"type": "bearer", "token": (directory / "mcp.bearer").read_text("ascii")},
            )
        )
        if not discovery.reachable or set(discovery.tools) != {
            "create_incident_handoff",
            "purge_incident_history",
        }:
            raise RuntimeError("Real MCP discovery blocked")
        result["mcp_reachability"] = "PASS"
        server.start()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=False)
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.set_default_timeout(40000)
            page.goto(server.url)
            page.locator("#capability-file").set_input_files(args.state / "capability")
            expect(page.locator("#capability-status")).to_contain_text("Workspace unlocked")
            if args.resume_run:
                saved = server.get(f"/api/runs/{args.resume_run}")
                if saved["state"] != "AwaitingApproval":
                    raise ValueError("Resume only an unapproved Plan; never redispatch an Action")
                page.locator("#restore-id").fill(str(args.resume_run))
                page.locator("#restore").click()
            else:
                page.locator("#intent").fill(
                    "Create a synthetic handoff for INC-2042. "
                    "Investigate checkout errors and preserve notes."
                )
                page.locator("#generate").click()
            expect(page.locator("#run-state")).to_have_text("AwaitingApproval", timeout=35000)
            run_id = page.locator("#restore-id").input_value()
            page.locator("#approve").click()
            expect(page.locator("#run-state")).to_have_text("Approved")
            page.locator("#admit").click()
            expect(page.locator("#action-state")).to_have_text("Pending")
            page.locator("#try-unauthorized").click()
            expect(page.locator("#error")).to_contain_text("ACTION_NOT_EXECUTABLE")
            assert not store.records()
            page.locator("#authorize").click()
            expect(page.locator("#action-state")).to_have_text("Authorized")
            page.locator("#execute").click()
            expect(page.locator("#action-state")).to_have_text(
                re.compile("Succeeded|Failed|Unknown"), timeout=12000
            )
            action = json.loads(page.locator("#action-json").text_content())
            result["action"] = action
            page.screenshot(path=str(args.output / "real-allowed-attempt.png"), full_page=True)
            assert action["state"] == "Succeeded"
            records = store.records()
            assert len(records) == 1
            assert records[0]["receipt_reference"] == action["result"]["receipt_reference"]
            with sqlite3.connect(store.path) as db:
                assert db.execute("SELECT count(*) FROM handoffs").fetchone()[0] == 1
            result.update(allowed_invocation="PASS", one_durable_effect="PASS", action=action)
            page.screenshot(path=str(args.output / "real-allowed.png"), full_page=True)
            page.locator("#replay").click()
            expect(page.locator("#notice")).to_contain_text("receipt is unchanged")
            tested_canary_now = not canary_attempted
            if tested_canary_now:
                page.locator("#policy-test").click()
                canary_attempted = True
                expect(page.locator("#policy-result")).to_contain_text(
                    '"policy_denial_verified": true', timeout=12000
                )
                denial = json.loads(page.locator("#policy-result").text_content())
                result["denial"] = denial
                assert denial["status"] == "ARMORIQ_POLICY_DENIED" and store.records() == records
            result.update(
                policy_denial="PASS", no_forbidden_effect="PASS", no_double_execution="PASS"
            )
            if tested_canary_now:
                page.screenshot(path=str(args.output / "real-denied.png"), full_page=True)
            page.reload()
            page.locator("#capability-file").set_input_files(args.state / "capability")
            expect(page.locator("#action-state")).to_have_text("Succeeded")
            assert store.records() == records
            result["browser_refresh"] = "PASS"
            result["run"] = server.get(f"/api/runs/{run_id}")
            result["events"] = server.get("/api/policy/evidence")["events"]
            browser.close()
        server.stop()
        server.start()
        assert server.get(f"/api/actions/{action['action_id']}")["state"] == "Succeeded"
        assert store.records() == records
        result["restart_recovery"] = "PASS"
        # Cloud assignment and actual dashboard audit still require independent evidence.
        result["invocation_checks"] = "PASS"
    except Exception as exc:
        result["error_class"] = type(exc).__name__
    finally:
        if server.process is not None and server.process.poll() is None:
            # Preserve partial results. A failed write path never triggers another write.
            try:
                if not canary_attempted:
                    canary_attempted = True
                    response = httpx.post(
                        server.url + "/api/policy/test",
                        headers=server.headers,
                        json={"operation": "purge_incident_history"},
                        timeout=12,
                        trust_env=False,
                    )
                    result["denial"] = response.json()
                    result["policy_denial"] = (
                        "PASS" if result["denial"].get("policy_denial_verified") else "BLOCKED"
                    )
                if run_id is not None:
                    result["run"] = server.get(f"/api/runs/{run_id}")
                    result["actions"] = server.get(f"/api/runs/{run_id}/actions")
                result["events"] = server.get("/api/policy/evidence")["events"]
                result["final_record_count"] = len(store.records())
            except Exception as exc:
                result["partial_evidence_error_class"] = type(exc).__name__
        server.stop()
        client.close()
        (args.output / "real-evidence.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key not in {"run", "action", "actions", "events"}
            }
        )
    )
    if result.get("invocation_checks") != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
