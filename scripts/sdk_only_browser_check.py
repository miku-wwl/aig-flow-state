"""Review first; an explicit approval file permits one synthetic browser write.

No direct planning/approval/admission/authorization/execute API calls. No HAR or
network trace. Existing state is never provisioned over or used for a new effect.
"""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from safeops.integration.dispatch_permit import provision_live
from safeops.integration.runtime_composition import provision
from tests.server_harness import ServerHarness


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume-review", type=Path)
    parser.add_argument("--resume-authorized", help="Exact never-executed Authorized Action UUID")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    prior = json.loads(args.resume_review.read_text("utf-8")) if args.resume_review else None
    if prior is None:
        provision(args.state)  # exclusive fresh state, never reopen an old Action
        provision_live(args.state)
    server = ServerHarness(args.state, provider="ollama", enforcement_mode="sdk-only")
    result = {"transport": "REAL_PLATFORM", "clicks": [], "qualification": "NOT_RUN"}

    def save(name, data):
        (args.output / name).write_text(json.dumps(data, indent=2), encoding="utf-8")

    try:
        server.start()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=False)
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.set_default_timeout(35000)
            page.goto(server.url)
            page.locator("#capability-file").set_input_files(args.state / "capability")
            expect(page.locator("#capability-status")).to_contain_text("Workspace unlocked")
            expect(page.locator("#mode-chip")).to_have_text("ARMORIQ SDK-ONLY LIVE")
            page.locator("#intent").fill(
                "Create one synthetic incident handoff for INC-24001. "
                "Summary: Synthetic Phase 2.4 browser qualification. "
                "Handoff note: Synthetic test only; no operational incident or external recipient."
            )

            def click(selector, label):
                before = time.perf_counter()
                page.locator(selector).click()
                result["clicks"].append(
                    {
                        "label": label,
                        "utc": datetime.now(UTC).isoformat(),
                        "click_ms": round((time.perf_counter() - before) * 1000, 3),
                    }
                )

            if prior is None:
                click("#generate", "Generate real Ollama Plan")
            else:
                existing = server.get(f"/api/runs/{prior['run_id']}/actions")["actions"]
                if args.resume_authorized:
                    assert len(existing) == 1
                    assert existing[0]["action_id"] == args.resume_authorized
                    assert existing[0]["state"] == "Authorized" and existing[0]["version"] == 2
                else:
                    assert existing == []
                page.locator("#restore-id").fill(prior["run_id"])
                click("#restore", "Open the same saved real Ollama Run")
            expect(page.locator("#run-state")).to_have_text(
                "Approved" if args.resume_authorized else "AwaitingApproval", timeout=35000
            )
            plan = json.loads(page.locator("#plan-json").text_content())
            result["reviewed_plan"] = plan
            result["run_id"] = page.locator("#restore-id").input_value()
            result["provider"] = (
                prior["provider"] if prior else server.get("/api/status")["provider"]
            )
            if prior:
                assert prior["run_id"] == result["run_id"] and prior["reviewed_plan"] == plan
                result["original_generation_evidence"] = str(args.resume_review)
                result["original_browser_clicks"] = (
                    prior.get("original_browser_clicks", []) + prior["clicks"]
                )
            assert result["provider"]["mode"] == "ollama"
            assert result["provider"]["model"] == "phi4-mini:latest"
            assert result["provider"]["calls"] == result["provider"]["responses"] == 1
            assert plan["steps"][0]["arguments"]["incident_id"] == "INC-24001"
            assert server.get("/api/handoffs")["records"] == []
            page.screenshot(
                path=str(
                    args.output
                    / (
                        "01-approved-restored.png"
                        if args.resume_authorized
                        else "01-new-plan-awaiting-approval.png"
                    )
                ),
                full_page=True,
            )
            save("review.json", result)
            print(
                json.dumps(
                    {
                        "status": "AWAITING_EXPLICIT_USER_APPROVAL",
                        "run_id": result["run_id"],
                        "plan": plan,
                    }
                ),
                flush=True,
            )
            # No timeout or missing input can count as approval.
            approval_file = args.output / "operator-approval.json"
            while not approval_file.exists():
                time.sleep(0.5)
            approval = json.loads(approval_file.read_text("utf-8"))
            if approval != {
                "decision": "APPROVE_ONE_WRITE",
                "run_id": result["run_id"],
                "arguments": plan["steps"][0]["arguments"],
            }:
                result["qualification"] = "APPROVAL_NOT_RECEIVED"
                return
            result["approval_source"] = (
                "Explicit user approval of review.json, then actual Chrome clicks"
            )
            if not args.resume_authorized:
                click("#approve", "Approve exact reviewed Plan")
                expect(page.locator("#run-state")).to_have_text("Approved")
                click("#admit", "Admit approved Action")
                expect(page.locator("#action-state")).to_have_text("Pending")
                click("#try-unauthorized", "Prove missing independent authorization is denied")
                expect(page.locator("#error")).to_contain_text("ACTION_NOT_EXECUTABLE")
                assert server.get("/api/handoffs")["records"] == []
                click("#authorize", "Independently authorize Action")
            expect(page.locator("#action-state")).to_have_text("Authorized")
            expect(page.locator("#prepare-sdk")).to_be_enabled()
            page.screenshot(path=str(args.output / "02-authorized-no-effect.png"), full_page=True)
            before = time.perf_counter()
            click("#prepare-sdk", "Prestage exact Authorized Action")
            expect(page.locator("#sdk-stage-status")).to_contain_text("READY", timeout=35000)
            result["prestage_ui_ms"] = round((time.perf_counter() - before) * 1000, 3)
            assert server.get("/api/handoffs")["records"] == []
            page.screenshot(path=str(args.output / "03-prestaged-no-effect.png"), full_page=True)
            before = time.perf_counter()
            click("#execute", "One live business execution")
            expect(page.locator("#action-state")).to_have_text("Succeeded", timeout=35000)
            expect(page.locator("#sdk-audit-status")).to_contain_text(
                "SDK_AUDIT_POST_ACKNOWLEDGED", timeout=35000
            )
            result["execute_ui_including_post_core_audit_ms"] = round(
                (time.perf_counter() - before) * 1000, 3
            )
            action = json.loads(page.locator("#action-json").text_content())
            result["action"] = action
            result["stage"] = server.get(f"/api/actions/{action['action_id']}/sdk-stage")
            records = server.get("/api/handoffs")["records"]
            assert len(records) == 1 and records[0]["incident_id"] == "INC-24001"
            assert records[0]["receipt_reference"] == action["result"]["receipt_reference"]
            result["records"] = records
            before_audit = server.get("/api/policy/evidence")
            click("#replay", "Exact Core idempotency replay")
            expect(page.locator("#notice")).to_contain_text("receipt is unchanged")
            assert server.get("/api/handoffs")["records"] == records
            assert server.get("/api/policy/evidence") == before_audit
            page.screenshot(
                path=str(args.output / "04-new-success-receipt-audit.png"), full_page=True
            )
            page.reload()
            page.locator("#capability-file").set_input_files(args.state / "capability")
            expect(page.locator("#action-state")).to_have_text("Succeeded")
            expect(page.locator("#receipt")).to_have_text(action["result"]["receipt_reference"])
            assert server.get("/api/handoffs")["records"] == records
            assert server.get("/api/policy/evidence") == before_audit
            page.screenshot(path=str(args.output / "05-refresh-restored.png"), full_page=True)
            server.stop()
            server.start()
            page.reload()
            page.locator("#capability-file").set_input_files(args.state / "capability")
            expect(page.locator("#action-state")).to_have_text("Succeeded")
            expect(page.locator("#receipt")).to_have_text(action["result"]["receipt_reference"])
            assert server.get("/api/handoffs")["records"] == records
            assert server.get("/api/policy/evidence") == before_audit
            result["refresh_restart_preserved"] = True
            page.screenshot(
                path=str(args.output / "06-process-restart-restored.png"), full_page=True
            )
            result["qualification"] = "PASS"
            browser.close()
    except Exception as error:
        result["qualification"] = "BLOCKED"
        result["error_type"] = type(error).__name__
        # Preserve available evidence without retrying any failed/Unknown Action.
        if server.process and server.process.poll() is None and result.get("run_id"):
            result["actions_at_failure"] = server.get(f"/api/runs/{result['run_id']}/actions")
            result["records_at_failure"] = server.get("/api/handoffs")
            result["audit_at_failure"] = server.get("/api/policy/evidence")
    finally:
        server.stop()
        save("result.json", result)
        print(
            json.dumps(
                {"qualification": result["qualification"], "error_type": result.get("error_type")}
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
