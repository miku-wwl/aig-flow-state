"""Real Chrome clicks against FastAPI + actual SDK, explicitly OFFLINE network."""

import json

import pytest
from playwright.sync_api import expect, sync_playwright

from tests.browser.test_e2e import admit, generate, unlock
from tests.server_harness import ServerHarness, artifact_directory, save_evidence

pytestmark = pytest.mark.browser


@pytest.mark.parametrize(
    "fault,terminal,audit",
    [
        ("none", "Succeeded", "SDK_AUDIT_POST_ACKNOWLEDGED"),
        ("deny", "Failed", "SDK_FAILED"),
        ("report_error", "Succeeded", "SDK_AUDIT_UNVERIFIED"),
    ],
)
def test_sdk_only_clicks_and_persisted_restore(state, fault, terminal, audit):
    server = ServerHarness(state, enforcement_mode="sdk-only", offline_sdk=True, sdk_fault=fault)
    try:
        server.start()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.set_default_timeout(15000)
            generate(page, server)
            expect(page.locator("#mode-chip")).to_have_text("LOCAL / OFFLINE SDK TEST")
            expect(page.locator("#prepare-sdk")).to_be_disabled()
            admit(page)
            expect(page.locator("#prepare-sdk")).to_be_disabled()
            page.locator("#try-unauthorized").click()
            expect(page.locator("#error")).to_contain_text("ACTION_NOT_EXECUTABLE")
            page.locator("#authorize").click()
            expect(page.locator("#action-state")).to_have_text("Authorized")
            expect(page.locator("#sdk-stage-status")).to_contain_text("MISSING")
            expect(page.locator("#execute")).to_be_disabled()
            page.locator("#prepare-sdk").click()
            expect(page.locator("#sdk-stage-status")).to_contain_text("READY")
            permit_evidence = page.locator("#timeline .evidence-entry").filter(
                has_text="Consumer permit / argument validation"
            )
            expect(permit_evidence).to_have_attribute("data-state", "pending")
            assert server.get("/api/handoffs")["records"] == []
            page.locator("#execute").click()
            expect(page.locator("#action-state")).to_have_text(terminal)
            expect(page.locator("#sdk-audit-status")).to_contain_text(audit)
            if terminal == "Succeeded":
                expect(permit_evidence).to_have_attribute("data-state", "complete")
            expect(page.locator('[data-step="preparation"]')).to_have_attribute(
                "data-state", "complete"
            )
            expected_policy = (
                "Explicit Allow NOT CONFIRMED" if fault == "deny" else "Explicit Allow CONFIRMED"
            )
            expect(page.locator("#sdk-policy-status")).to_contain_text("OFFLINE SDK fixture")
            expect(page.locator("#sdk-policy-status")).to_contain_text(expected_policy)
            expect(page.locator('[data-step="preparation"]')).to_have_attribute(
                "data-state", "complete"
            )
            action = json.loads(page.locator("#action-json").text_content())
            records = server.get("/api/handoffs")["records"]
            assert len(records) == (0 if terminal == "Failed" else 1)
            page.locator("#replay").click()
            expect(page.locator("#notice")).to_contain_text("receipt is unchanged")
            assert server.get("/api/handoffs")["records"] == records
            page.reload()
            unlock(page, server)
            expect(page.locator("#action-state")).to_have_text(terminal)
            expect(page.locator("#sdk-audit-status")).to_contain_text(audit)
            expect(page.locator("#sdk-policy-status")).to_contain_text(expected_policy)
            output = artifact_directory("screenshots")
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output / f"phase24-offline-sdk-{fault}.png"), full_page=True)
            save_evidence(
                f"phase24-offline-sdk-{fault}", {"platform": "OFFLINE_TEST", "action": action}
            )
            browser.close()
        server.stop()
        server.start()
        assert server.get(f"/api/actions/{action['action_id']}")["state"] == terminal
        assert server.get("/api/handoffs")["records"] == records
        assert (
            server.get(f"/api/actions/{action['action_id']}/sdk-stage")["audit"]["status"] == audit
        )
        policy = server.get(f"/api/actions/{action['action_id']}/sdk-stage")["policy"]
        assert policy["transport"] == "OFFLINE_TEST"
        assert policy["explicit_allow_confirmed"] == (terminal == "Succeeded")
    finally:
        server.stop()


def test_historical_denial_reference_is_explicit_and_read_only(state):
    server = ServerHarness(state, enforcement_mode="sdk-only", offline_sdk=True)
    try:
        server.start()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            page.set_default_timeout(15000)
            page.goto(server.url)
            expect(page.locator("#mode-chip")).to_have_text("LOCAL / OFFLINE SDK TEST")
            unlock(page, server)
            expect(page.locator("#policy-origin-label")).to_contain_text(
                "OFFLINE TEST MODE"
            )
            before_records = server.get("/api/handoffs")["records"]
            before_events = server.get("/api/policy/evidence")["events"]
            page.locator("#policy-test").click()
            expect(page.locator("#policy-origin-label")).to_have_text(
                "HISTORICAL ARMORIQ POLICY DENIAL · NOT THIS RUN"
            )
            expect(page.locator("#policy-result")).to_contain_text(
                "Historical Phase 2.2 evidence; no fresh request"
            )
            expect(page.locator("#policy-result")).to_contain_text("NOT_RUN_IN_PHASE24")
            expect(page.locator("#policy-result")).to_contain_text("Core Action created: No")
            expect(page.locator("#policy-result")).to_contain_text("Business effect executed: No")
            assert server.get("/api/handoffs")["records"] == before_records == []
            assert server.get("/api/policy/evidence")["events"] == before_events == []
            page.evaluate("window.scrollTo(0, 0)")
            output = artifact_directory("screenshots")
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output / "historical-denial-reference-offline-1920x1080.png"))
            save_evidence(
                "historical-denial-reference-offline",
                {"platform_request": "NOT_RUN", "core_actions": 0, "handoffs": 0},
            )
            browser.close()
    finally:
        server.stop()
