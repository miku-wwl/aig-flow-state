"""Separate headed-browser check: real installed phi4-mini through local Ollama."""

import argparse
import json
import re
import sqlite3
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from safeops.integration.runtime_composition import provision
from tests.server_harness import ServerHarness, save_evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=Path(".runtime/local"))
    args = parser.parse_args()
    # This is a verification command, explicitly allowed to initialize NEW state.
    if not args.state.exists():
        provision(args.state)
    with httpx.Client(trust_env=False, timeout=10) as client:
        response = client.get("http://127.0.0.1:11434/api/tags")
        response.raise_for_status()
        names = [model["name"] for model in response.json()["models"]]
    if "phi4-mini:latest" not in names:
        raise RuntimeError("LIVE_OLLAMA_E2E=BLOCKED: local phi4-mini:latest is not installed")
    server = ServerHarness(args.state, provider="ollama")
    screenshots = Path(".artifacts/screenshots")
    screenshots.mkdir(parents=True, exist_ok=True)
    try:
        server.start()
        before = server.get("/api/handoffs")["records"]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=False)
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.set_default_timeout(40000)
            page.goto(server.url)
            expect(page.locator("#provider-mode")).to_contain_text("Live local Ollama")
            page.locator("#capability-file").set_input_files(args.state / "capability")
            expect(page.locator("#capability-status")).to_contain_text("Workspace unlocked")
            page.locator("#intent").fill(
                "Create an incident handoff for INC-1042. The checkout API is returning errors. "
                "The team should investigate the upstream dependency and preserve notes."
            )
            page.locator("#generate").click()
            # Wait for the actual response, then save a failure without inventing a Plan.
            expect(page.locator("#run-state")).to_have_text(
                re.compile("AwaitingApproval|PlanRejected"), timeout=35000
            )
            run_id = page.locator("#restore-id").input_value()
            run = server.get(f"/api/runs/{run_id}")
            status = server.get("/api/status")
            if run["state"] != "AwaitingApproval":
                page.screenshot(path=str(screenshots / "live-ollama-failure.png"), full_page=True)
                save_evidence("live-ollama-failure", {"run": run, "status": status})
                raise RuntimeError(
                    "LIVE_OLLAMA_E2E=FAIL: inspect sanitized live-ollama-failure evidence"
                )
            assert status["provider"]["mode"] == "ollama"
            assert status["provider"]["responses"] == 1
            assert status["provider"]["model"] == "phi4-mini:latest"
            page.screenshot(
                path=str(screenshots / "live-plan-awaiting-approval.png"), full_page=True
            )
            page.locator("#approve").click()
            expect(page.locator("#run-state")).to_have_text("Approved")
            page.locator("#admit").click()
            expect(page.locator("#action-state")).to_have_text("Pending")
            page.locator("#authorize").click()
            expect(page.locator("#action-state")).to_have_text("Authorized")
            page.locator("#execute").click()
            expect(page.locator("#action-state")).to_have_text("Succeeded")
            receipt = page.locator("#receipt").inner_text()
            action = json.loads(page.locator("#action-json").text_content())
            records = server.get("/api/handoffs")["records"]
            assert len(records) == len(before) + 1
            record = next(item for item in records if item["receipt_reference"] == receipt)
            with sqlite3.connect(args.state / "effects.sqlite3") as db:
                assert (
                    db.execute(
                        "SELECT count(*) FROM handoffs WHERE receipt_reference=?", (receipt,)
                    ).fetchone()[0]
                    == 1
                )
            expect(page.locator(f".record[data-receipt='{receipt}']")).to_be_visible()
            page.screenshot(path=str(screenshots / "live-successful-action.png"), full_page=True)
            evidence = {
                "installed_models": names,
                "provider": status["provider"],
                "run": run,
                "action": action,
                "record": record,
                "real_http": True,
                "headed_browser": True,
            }
            save_evidence("live-ollama", evidence)
            browser.close()
        print(
            json.dumps(
                {
                    "LIVE_OLLAMA_E2E": "PASS",
                    "model": status["provider"]["model"],
                    "action_id": action["action_id"],
                    "receipt": receipt,
                }
            )
        )
    finally:
        server.stop()


if __name__ == "__main__":
    main()
