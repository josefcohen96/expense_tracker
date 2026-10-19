"""The pages whose scripts live in static/js/pages/, opened in a real browser.

Guards the move of the inline page scripts out of the templates: every page loads at a phone and a
desktop viewport without a page error or a console error, every /static/js/pages/*.js it asks for
comes back 200, and one element of the page is there (so the template really rendered).

Headless Chromium (Playwright) against the app served by uvicorn on a free port, like
test_workouts_arena_browser.py. Skips itself when Playwright or its Chromium is not installed.
"""
import socket
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

VIEWPORTS = {
    "phone": {"width": 393, "height": 852},
    "desktop": {"width": 1280, "height": 800},
}

# (path, selector of an element that exists on an empty database). "{vendor_id}" is filled in.
PAGES = [
    ("/wedding/guests", "#guest-search"),
    ("/wedding/vendors", "#filter-chips"),
    ("/wedding/vendors/{vendor_id}", "#vendor-form"),
    ("/wedding/seating", "#guests-panel"),
    ("/finances/transactions", "#filters-body"),
    ("/finances/transactions/import", "#ci-file"),
    ("/wedding/milestones", "#ms-rail, #ms-cta-form"),  # rail with a wedding date, CTA without
    ("/wedding/timeline", "#timeline-grid"),
    ("/wedding/overseas", "#ov-board"),
    ("/wedding/tasks", "#task-board"),
    ("/workouts/admin", "#session-modal"),
    ("/wedding/lodging", "#room-modal"),
    ("/wedding/budget", "#add-item-modal"),
    ("/wedding/ideas", "#idea-modal"),
    ("/renovation/journal", "#journal-modal"),
]

# Console errors a page already logs on main, as (path, substring). Empty: none found.
ALLOWED_CONSOLE_ERRORS: list[tuple[str, str]] = []

IGNORED = ("favicon", "cdn.jsdelivr.net")


# ----------------------------------------------------------------------------- fixtures

def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server(app_client):
    """The same app (and temp DB) the TestClient uses, served over HTTP for the browser."""
    import uvicorn

    import app.backend.app.main as main_app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(main_app.app, host="127.0.0.1", port=port, log_level="warning", log_config=None))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started:
        if time.time() > deadline or not thread.is_alive():
            pytest.fail("uvicorn did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(10)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch()
        except Exception as error:  # no browser downloaded on this machine
            pytest.skip(f"Chromium unavailable: {error}")
        yield chromium
        chromium.close()


@pytest.fixture(scope="module")
def vendor_id(app_client):
    r = app_client.post(
        "/api/wedding/vendors",
        json={"name": "ספק לבדיקת דפדפן", "category": "venue", "status": "not_contacted"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ----------------------------------------------------------------------------- the test

def _ignored(text: str, url: str) -> bool:
    return any(token in text or token in url for token in IGNORED)


def _allowed(path: str, text: str) -> bool:
    return any(path == p and fragment in text for p, fragment in ALLOWED_CONSOLE_ERRORS)


@pytest.mark.parametrize("viewport", list(VIEWPORTS))
@pytest.mark.parametrize(("path", "selector"), PAGES, ids=[p for p, _ in PAGES])
def test_page_runs_its_script_cleanly(browser, live_server, vendor_id, path, selector, viewport):
    path = path.format(vendor_id=vendor_id)
    context = browser.new_context(viewport=VIEWPORTS[viewport], locale="he-IL")
    page = context.new_page()
    page.on("dialog", lambda dialog: dialog.dismiss())

    page_errors: list[str] = []
    console_errors: list[str] = []
    page_scripts: list[tuple[str, int]] = []

    page.on("pageerror", lambda error: page_errors.append(str(error)))

    def on_console(msg):
        if msg.type != "error":
            return
        url = (msg.location or {}).get("url", "")
        if _ignored(msg.text, url) or _allowed(path, msg.text):
            return
        console_errors.append(f"{msg.text} ({url})")

    page.on("console", on_console)

    def on_response(response):
        if "/static/js/pages/" in response.url:
            page_scripts.append((response.url, response.status))

    page.on("response", on_response)

    try:
        response = page.goto(f"{live_server}{path}", wait_until="load")
        assert response is not None and response.status == 200, f"{path} → {response and response.status}"
        assert page.locator(selector).count() == 1, f"{selector} missing on {path}"
        assert page_errors == [], page_errors
        assert console_errors == [], console_errors
        for url, status in page_scripts:
            assert status in (200, 304), f"{url} → {status}"  # 304 = revalidated from the browser cache
    finally:
        context.close()
