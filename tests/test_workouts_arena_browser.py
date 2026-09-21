"""The arena as the phone sees it: set → rest → next set, a hold timer, a refresh mid-workout,
and the plain-arena fallback when the hologram cannot load.

The other workouts suites drive the routes with TestClient; these open the real page in a
headless Chromium (Playwright) against the app served by uvicorn on a free port. They skip
themselves when Playwright or its Chromium is not installed, so the plain suite still runs.
"""
import socket
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright  # noqa: E402

MU_BASIC = "עליות מתח בסיסיות (Basic Pull-ups)"       # muscle_up station 0 — 4 × 10 reps
MU_TITLE = "עליות מתח בסיסיות"                           # what the arena shows (the Hebrew half)
HS_WALL = "עמידת ידיים לקיר (החזקה) (Wall-Assisted Handstand Hold)"  # hspu station 0 — a 30 s hold

PHONE = {"width": 393, "height": 852}
CDN = "https://cdn.jsdelivr.net/**"


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


@pytest.fixture()
def clean_workouts(db_conn):
    def wipe():
        db_conn.execute("DELETE FROM workouts")
        db_conn.commit()
    wipe()
    yield
    wipe()


@pytest.fixture()
def page(browser, live_server, clean_workouts):
    """A fresh phone-sized context per test (own localStorage), CDN blocked, dialogs accepted."""
    context = browser.new_context(viewport=PHONE, locale="he-IL")
    context.route(CDN, lambda route: route.abort())
    pg = context.new_page()
    pg.on("dialog", lambda dialog: dialog.accept())
    pg.goto(f"{live_server}/workouts")
    yield pg
    context.close()


# ----------------------------------------------------------------------------- helpers

def _arena(page):
    return page.locator("#arena")


def _set_panel(page):
    return page.locator('[data-phase-panel="set"]')


def _start_path(page, key):
    page.locator(f'[data-start-path="{key}"]').first.click()
    expect(_arena(page)).to_be_visible()
    expect(_arena(page)).to_have_attribute("data-phase", "warmup")
    page.get_by_role("button", name="דילוג על החימום").click()
    expect(_arena(page)).to_have_attribute("data-phase", "set")


def _after_set(page):
    """A completed set leads to the rest screen, or straight to 'complete' after the last one."""
    page.wait_for_function(
        "() => document.querySelector('#arena').dataset.phase === 'rest'"
        " || document.querySelector('[data-phase-panel=\"set\"]').dataset.state === 'complete'"
    )
    return _arena(page).get_attribute("data-phase")


def _rest_then_next(page):
    page.get_by_role("button", name="אני מוכן").click()
    expect(_arena(page)).to_have_attribute("data-phase", "set")


def _rows(db_conn, name):
    return db_conn.execute(
        "SELECT total_sets, total_reps, max_reps FROM workouts WHERE exercise_name = ?", (name,)
    ).fetchall()


# ----------------------------------------------------------------------------- tests

def test_reps_path_runs_set_rest_set_and_saves(page, db_conn):
    _start_path(page, "muscle_up")
    panel = _set_panel(page)
    expect(panel).to_have_attribute("data-state", "active")
    expect(panel).to_have_attribute("data-unit", "reps")
    expect(page.locator("#arena-reps")).to_have_text("10")
    expect(page.locator("#arena-ex-name")).to_have_text(MU_TITLE)
    expect(page.locator("#arena-set-label")).to_contain_text("1")

    # First set → rest → second set
    page.locator("#arena-done-btn").click()
    assert _after_set(page) == "rest"
    expect(page.locator("#rest-next-title")).to_be_visible()
    _rest_then_next(page)
    expect(page.locator("#arena-set-label")).to_contain_text("2")

    # The remaining sets, then the workout is ready to save
    for _ in range(3):
        page.locator("#arena-done-btn").click()
        if _after_set(page) == "rest":
            _rest_then_next(page)
    expect(panel).to_have_attribute("data-state", "complete")
    expect(page.locator("#finish-workout-btn")).to_be_visible()

    page.locator("#finish-workout-btn").click()
    expect(_arena(page)).to_have_attribute("data-phase", "reward")
    expect(page.locator("#reward-total")).not_to_be_empty()

    rows = _rows(db_conn, MU_BASIC)
    assert [tuple(r) for r in rows] == [(4, 40, 10)]


def test_hold_station_stopping_early_saves_seconds_really_held(page, db_conn):
    _start_path(page, "hspu")
    panel = _set_panel(page)
    expect(panel).to_have_attribute("data-unit", "sec")
    expect(panel).to_have_attribute("data-hold", "idle")
    expect(page.locator("#arena-reps")).to_have_text("30")
    expect(page.locator("#arena-reps-label")).to_contain_text("שניות")
    # A hold starts with its own button; the rep "done" button is not offered while idle
    expect(page.locator("#arena-hold-btn")).to_be_visible()
    expect(page.locator("#arena-done-btn")).to_be_hidden()

    page.locator("#arena-hold-btn").click()
    expect(panel).to_have_attribute("data-hold", "running")
    expect(page.locator("#arena-reps-label")).to_have_text("שניות נשארו")
    expect(page.locator("#arena-done-label")).to_contain_text("עצור")
    page.wait_for_timeout(1500)
    page.locator("#arena-done-btn").click()          # stop early
    assert _after_set(page) == "rest"

    # Finish now, leaving the other sets undone (the confirm dialog is auto-accepted)
    _rest_then_next(page)
    page.get_by_role("button", name="כל התרגילים").click()
    page.locator("#arena-finish-early").click()
    expect(_arena(page)).to_have_attribute("data-phase", "reward")

    rows = _rows(db_conn, HS_WALL)
    assert len(rows) == 1
    sets, reps, best = rows[0]
    assert sets == 1
    assert 1 <= best <= 4, "the seconds really held are saved, not the 30 s target"
    assert reps == best


def test_workout_survives_a_page_refresh(page, live_server):
    _start_path(page, "muscle_up")
    page.locator("#arena-done-btn").click()
    assert _after_set(page) == "rest"

    page.reload()
    expect(_arena(page)).to_be_visible()
    expect(_arena(page)).to_have_attribute("data-phase", "rest")
    _rest_then_next(page)
    expect(page.locator("#arena-set-label")).to_contain_text("2")
    expect(page.locator("#arena-ex-name")).to_have_text(MU_TITLE)


def test_plain_arena_when_the_hologram_cannot_load(page):
    """The model viewer comes from a CDN; with it unreachable the set screen keeps the cues."""
    _start_path(page, "muscle_up")
    panel = _set_panel(page)
    expect(panel).to_have_attribute("data-holo", "off")
    expect(page.locator("#arena-cues")).to_be_visible()
    expect(page.locator("#arena-cues .arena-cue")).to_have_count(2)
    expect(page.locator("#arena-tempo")).to_be_visible()
    expect(page.locator(".holo-block .holo-stage")).to_be_hidden()
    expect(page.locator("#holo-form-btn")).to_be_hidden()
