import json
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from tests.browser.test_e2e import admit, generate, unlock
from tests.server_harness import ServerHarness, save_evidence

pytestmark = pytest.mark.browser


@pytest.mark.parametrize(
    "fault,expected",
    [("none", "Succeeded"), ("deny", "Failed"), ("timeout_after_commit", "Unknown")],
)
def test_live_ui_with_offline_sdk_transport(state, fault, expected):
    """Real browser/server/SDK/MCP, offline platform. Never claim cloud policy evidence."""
    harness = ServerHarness(state, enforcement_mode="real", offline_sdk=True, sdk_fault=fault)
    try:
        harness.start()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.set_default_timeout(15000)
            generate(page, harness)
            expect(page.locator("#mode-chip")).to_have_text("LOCAL / OFFLINE SDK TEST")
            expect(page.locator("#enforcement-mode")).to_contain_text(
                "no real platform enforcement"
            )
            expect(page.locator("#enforcement-mode")).not_to_contain_text("Phase 1")
            admit(page)
            page.locator("#authorize").click()
            expect(page.locator("#action-state")).to_have_text("Authorized")
            page.locator("#execute").click()
            expect(page.locator("#action-state")).to_have_text(expected)
            expect(page.locator("#live-evidence")).to_contain_text(
                "ALLOWED_VERIFIED"
                if fault == "none"
                else "ARMORIQ_POLICY_DENIED"
                if fault == "deny"
                else "TIMEOUT"
            )
            records = harness.get("/api/handoffs")["records"]
            assert len(records) == (0 if fault == "deny" else 1)
            action = json.loads(page.locator("#action-json").text_content())
            page.reload()
            unlock(page, harness)
            expect(page.locator("#action-state")).to_have_text(expected)
            assert harness.get("/api/handoffs")["records"] == records
            directory = Path(".artifacts/screenshots")
            directory.mkdir(parents=True, exist_ok=True)
            page.screenshot(
                path=str(directory / f"phase2-offline-live-{fault}.png"), full_page=True
            )
            save_evidence(
                f"phase2-offline-live-{fault}",
                {"platform": "OFFLINE_TRANSPORT", "action": action, "record_count": len(records)},
            )
            browser.close()
        harness.stop()
        harness.start()
        assert harness.get(f"/api/actions/{action['action_id']}")["state"] == expected
        assert harness.get("/api/handoffs")["records"] == records
    finally:
        harness.stop()
