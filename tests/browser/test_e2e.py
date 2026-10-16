import hashlib
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

from tests.server_harness import ServerHarness, artifact_directory, save_evidence

pytestmark = pytest.mark.browser

SCREENSHOTS = artifact_directory("screenshots")


@pytest.fixture
def browser():
    with sync_playwright() as playwright:
        # Uses installed real Chrome; no model or browser download.
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        yield browser
        browser.close()


@pytest.fixture
def server(state):
    harness = ServerHarness(state)
    try:
        yield harness.start()
    finally:
        harness.stop()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 1100})
    page = context.new_page()
    page.set_default_timeout(15000)
    yield page
    context.close()


def unlock(page, server):
    page.locator("#capability-file").set_input_files(server.state / "capability")
    expect(page.locator("#capability-status")).to_contain_text("Workspace unlocked")


def assert_branding(page):
    expect(page).to_have_title("Aegis Relay — Govern AI Actions with ArmorIQ")
    expect(page.locator("h1")).to_have_text("Govern AI Actions with Real ArmorIQ Enforcement")
    expect(page.get_by_role("link", name="Aegis Relay home")).to_be_visible()
    expect(page.locator(".header-tagline")).to_have_text("Trust the intent. Govern the action.")
    expect(page.locator("meta[name='description']")).to_have_attribute(
        "content",
        "Aegis Relay governs AI actions with human approval, genuine ArmorIQ cloud enforcement evidence and verifiable receipts.",
    )
    expect(page.locator("#playground-title")).to_have_text("Interactive Governance Demo")
    expect(page.locator("main > section")).to_have_count(3)
    expect(page.locator("#playground-disclosure")).to_contain_text(
        "Sandbox mode: Real AI planning with simulated execution. No new ArmorIQ policy request is sent from this demo."
    )
    for obsolete in ["Phase 2.2", "LOCAL MOCK POLICY LAB", "Test local mock denial", "Persisted handoffs"]:
        expect(page.locator("body")).not_to_contain_text(obsolete)
    for removed_id in ["historical-denial", "policy-test", "restore-id", "try-unauthorized", "replay", "timeline"]:
        expect(page.locator(f"#{removed_id}")).to_have_count(0)
    expect(page.locator("body")).not_to_contain_text(re.compile(r"safe[\s_-]*ops\s+agent", re.I))


def generate(page, server):
    page.goto(server.url)
    assert_branding(page)
    expect(page.locator("#provider-mode")).to_contain_text("fixture")
    expect(page.locator("#workspace-state")).to_have_text("WORKSPACE LOCKED")
    unlock(page, server)
    page.locator("#intent").fill(
        "Create an incident handoff for INC-1042. The checkout API is returning errors. "
        "Investigate the upstream dependency and preserve notes."
    )
    page.locator("#generate").click()
    expect(page.locator("#run-state")).to_have_text("AwaitingApproval")
    expect(page.locator("#validation")).to_contain_text("SIDE_EFFECT")
    expect(page.locator('[data-step="plan"]')).to_have_attribute("data-state", "complete")
    expect(page.locator('[data-step="approval"]')).to_have_attribute("data-state", "current")


def admit(page):
    page.locator("#approve").click()
    expect(page.locator("#run-state")).to_have_text("Approved")
    expect(page.locator('[data-step="approval"]')).to_have_attribute("data-state", "complete")
    page.locator("#admit").click()
    expect(page.locator("#action-state")).to_have_text("Pending")
    expect(page.locator('[data-step="admission"]')).to_have_attribute("data-state", "complete")
    expect(page.locator('[data-step="authorization"]')).to_have_attribute("data-state", "current")


def execute(page):
    if page.locator("#authorize").is_enabled():
        page.locator("#authorize").click()
    expect(page.locator("#action-state")).to_have_text("Authorized")
    expect(page.locator('[data-step="authorization"]')).to_have_attribute("data-state", "complete")
    expect(page.locator('[data-step="execution"]')).to_have_attribute("data-state", "current")
    page.locator("#execute").click()
    expect(page.locator("#action-state")).to_have_text("Succeeded")
    expect(page.locator("#success-summary")).to_be_visible()
    expect(page.locator("#success-record")).to_contain_text("Matched persisted handoff")
    expect(page.locator('[data-step="execution"]')).to_have_attribute("data-state", "complete")
    expect(page.locator('[data-step="receipt"]')).to_have_attribute("data-state", "complete")


def screenshot(page, name):
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    assert page.locator("#capability-file").input_value() == ""
    page.screenshot(path=str(SCREENSHOTS / name), full_page=True)


def test_happy_governance_flow_and_read_only_refresh(page, server):
    generate(page, server)
    screenshot(page, "01-plan-awaiting-approval.png")
    run_id = page.locator("#run-id").text_content().replace("Run ID: ", "")
    admit(page)
    assert server.get("/api/handoffs")["records"] == []
    page.reload()
    unlock(page, server)
    expect(page.locator("#action-state")).to_have_text("Pending")
    expect(page.locator("#authorize")).to_be_enabled()
    assert server.get("/api/handoffs")["records"] == []
    page.locator("#authorize").click()
    expect(page.locator("#action-state")).to_have_text("Authorized")
    assert server.get("/api/handoffs")["records"] == []
    page.reload()
    unlock(page, server)
    expect(page.locator("#action-state")).to_have_text("Authorized")
    expect(page.locator("#execute")).to_be_enabled()
    assert server.get("/api/handoffs")["records"] == []
    execute(page)
    receipt = page.locator("#success-receipt").inner_text()
    action = json.loads(page.locator("#action-json").text_content())
    records = server.get("/api/handoffs")["records"]
    assert records[0]["receipt_reference"] == receipt
    assert server.get(f"/api/actions/{action['action_id']}")["state"] == "Succeeded"
    with sqlite3.connect(server.state / "effects.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM handoffs").fetchone()[0] == 1
        assert db.execute("SELECT receipt_reference FROM handoffs").fetchone()[0] == receipt
    screenshot(page, "02-successful-action-receipt.png")
    assert_branding(page)
    page.reload()
    expect(page.locator("#generate")).to_be_disabled()
    # Capability is intentionally not persisted; reload it, then refresh performs only reads.
    unlock(page, server)
    expect(page.locator("#action-state")).to_have_text("Succeeded")
    expect(page.locator("#success-receipt")).to_have_text(receipt)
    expect(page.locator("#success-record")).to_contain_text("Matched persisted handoff")
    assert server.get("/api/handoffs")["records"] == records
    screenshot(page, "03-persisted-after-refresh.png")
    assert_branding(page)
    save_evidence(
        "offline-browser",
        {
            "run_id": run_id,
            "action": action,
            "records": records,
            "screenshots": [str(path) for path in sorted(SCREENSHOTS.glob("0*.png"))],
            "state_directory": str(server.state),
        },
    )


def test_rejected_approval_no_effect(page, server):
    generate(page, server)
    page.locator("#reject").click()
    expect(page.locator("#run-state")).to_have_text("Rejected")
    expect(page.locator("#admit")).to_be_disabled()
    assert server.get("/api/handoffs")["records"] == []
    run_id = page.locator("#run-id").text_content().replace("Run ID: ", "")
    assert server.get(f"/api/runs/{run_id}/actions")["actions"] == []


def test_execution_without_authorization_denied(page, server):
    from uuid import uuid4

    generate(page, server)
    admit(page)
    action = json.loads(page.locator("#action-json").text_content())
    response = httpx.post(
        server.url + f"/api/actions/{action['action_id']}/execute",
        headers=server.headers | {"Idempotency-Key": str(uuid4())},
        json={"expected_action_version": action["version"]},
        trust_env=False,
        timeout=10,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ACTION_NOT_EXECUTABLE"
    expect(page.locator("#action-state")).to_have_text("Pending")
    assert server.get("/api/handoffs")["records"] == []


@pytest.mark.parametrize(
    "fault,code", [("timeout", "MODEL_TIMEOUT"), ("invalid_json", "PLAN_VALIDATION_ERROR")]
)
def test_provider_failure_rendered(page, state, fault, code):
    server = ServerHarness(state, fixture_fault=fault)
    try:
        server.start()
        page.goto(server.url)
        assert_branding(page)
        unlock(page, server)
        page.locator("#generate").click()
        expect(page.locator("#run-state")).to_have_text("PlanRejected")
        expect(page.locator("#error")).to_contain_text(code)
        expect(page.locator("#approve")).to_be_disabled()
        assert server.get("/api/handoffs")["records"] == []
    finally:
        server.stop()


def test_responsive_layout_and_browser_handlers(page, server):
    page_errors = []
    console_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.goto(server.url)
    for width, height in [(1920, 1080), (1440, 900), (768, 1024), (390, 844)]:
        page.set_viewport_size({"width": width, "height": height})
        expect(page.locator("#hero-title")).to_be_visible()
        expect(page.locator("#cloud-evidence")).to_have_count(1)
        overflow = page.evaluate(
            "({doc: document.documentElement.scrollWidth, body: document.body.scrollWidth, viewport: innerWidth})"
        )
        assert overflow["doc"] <= overflow["viewport"], f"horizontal overflow at {width}px: {overflow}"
        assert overflow["body"] <= overflow["viewport"], f"body overflow at {width}px: {overflow}"
        assert page_errors == []
        assert console_errors == []


def test_real_process_graceful_restart(page, server):
    generate(page, server)
    admit(page)
    execute(page)
    receipt = page.locator("#success-receipt").inner_text()
    run_id = page.locator("#run-id").text_content().replace("Run ID: ", "")
    action = json.loads(page.locator("#action-json").text_content())
    before = {
        name: hashlib.sha256((server.state / name).read_bytes()).hexdigest()
        for name in ["identity.json", "capability"]
    }
    previous_pid = server.process.pid
    records = server.get("/api/handoffs")["records"]
    server.stop()
    assert server.process.returncode == 0
    server.start()
    assert server.process.pid != previous_pid
    page.reload()
    unlock(page, server)
    expect(page.locator("#success-receipt")).to_have_text(receipt)
    expect(page.locator("#action-state")).to_have_text("Succeeded")
    assert server.get("/api/handoffs")["records"] == records
    after = {
        name: hashlib.sha256((server.state / name).read_bytes()).hexdigest() for name in before
    }
    assert before == after
    save_evidence(
        "restart-browser",
        {
            "run_id": run_id,
            "action_id": action["action_id"],
            "receipt": receipt,
            "before_pid": previous_pid,
            "after_pid": server.process.pid,
            "graceful_exit": 0,
            "identity_unchanged": before == after,
            "records": records,
        },
    )


def test_unknown_visible_without_redispatch(page, state):
    server = ServerHarness(state, executor_fault="post_commit_ack_loss")
    try:
        server.start()
        generate(page, server)
        admit(page)
        page.locator("#authorize").click()
        expect(page.locator("#action-state")).to_have_text("Authorized")
        page.locator("#execute").click()
        expect(page.locator("#action-state")).to_have_text("Unknown")
        expect(page.locator("#action-message")).to_contain_text("No automatic retry")
        expect(page.locator('[data-step="execution"]')).to_have_attribute("data-state", "unknown")
        records = server.get("/api/handoffs")["records"]
        assert len(records) == 1
        page.reload()
        unlock(page, server)
        expect(page.locator("#action-state")).to_have_text("Unknown")
        expect(page.locator("#execute")).to_be_disabled()
        assert server.get("/api/handoffs")["records"] == records
        save_evidence(
            "unknown-browser",
            {
                "action": json.loads(page.locator("#action-json").text_content()),
                "records": records,
                "duplicate_effects": False,
            },
        )
    finally:
        server.stop()


def test_concurrent_real_http_execute_after_browser_authorization(page, server):
    from uuid import uuid4

    generate(page, server)
    admit(page)
    page.locator("#authorize").click()
    expect(page.locator("#action-state")).to_have_text("Authorized")
    action = json.loads(page.locator("#action-json").text_content())
    headers = server.headers | {"Idempotency-Key": str(uuid4())}

    def send_request(_):
        return httpx.post(
            server.url + f"/api/actions/{action['action_id']}/execute",
            headers=headers,
            json={"expected_action_version": action["version"]},
            trust_env=False,
            timeout=10,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send_request, range(2)))
    assert all(response.status_code == 200 for response in responses)
    results = [response.json() for response in responses]
    assert sum(result["replayed"] for result in results) == 1
    page.reload()
    unlock(page, server)
    expect(page.locator("#action-state")).to_have_text("Succeeded")
    assert len(server.get("/api/handoffs")["records"]) == 1
    save_evidence("concurrent-http", {"requests": 2, "responses": results, "record_count": 1})
