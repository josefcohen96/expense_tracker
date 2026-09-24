"""The arena as the phone sees it: set → rest → next set, a hold timer, a refresh mid-workout,
the plain-arena fallback when the hologram cannot load, and the sound cues.

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
    # The warm-up never drops into the first set: the training waits for the start button.
    expect(_arena(page)).to_have_attribute("data-phase", "ready")
    page.get_by_role("button", name="התחל אימון", exact=True).click()
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


# A stand-in AudioContext that records the frequency of every note started. iPhones have no
# Vibration API, so the beeps are the only cue the phone can give; headless Chromium has no
# audio output, so this is also the only way to see them.
FAKE_AUDIO = """
window.__notes = [];
class FakeAudioContext {
    constructor() { this.state = 'running'; this.currentTime = 0; this.destination = {}; }
    resume() { return Promise.resolve(); }
    createGain() {
        const gain = { setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {} };
        return { gain, connect(node) { return node; } };
    }
    createOscillator() {
        const osc = { type: 'sine', frequency: { value: 0 }, connect(node) { return node; },
                      start() { window.__notes.push(osc.frequency.value); }, stop() {} };
        return osc;
    }
}
window.AudioContext = FakeAudioContext;
window.webkitAudioContext = undefined;
"""


def _notes(page):
    return page.evaluate("() => window.__notes")


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


def test_rest_and_hold_cues_beep_and_the_toggle_mutes_them(page):
    page.context.add_init_script(FAKE_AUDIO)
    page.reload()
    _start_path(page, "muscle_up")
    expect(page.locator("#arena-sound-btn")).to_have_attribute("aria-pressed", "true")

    # A logged set plays its two-note cue
    page.locator("#arena-done-btn").click()
    assert _after_set(page) == "rest"
    assert _notes(page) == [660, 880]

    # Pull the rest down to its last seconds: 3-2-1 ticks, then the "time's up" chord
    page.evaluate("() => adjustRestTimer(-(restRemainingSeconds() - 3))")
    page.wait_for_function("() => document.querySelector('#rest-ring-label').textContent === 'הזמן עבר'")
    notes = _notes(page)
    assert notes[2:5] == [880, 880, 880], notes
    assert notes[-3:] == [660, 660, 990], notes

    # Muting is remembered and silences the next cue
    page.locator("#arena-sound-btn").click()
    expect(page.locator("#arena-sound-btn")).to_have_attribute("aria-pressed", "false")
    assert page.evaluate("() => localStorage.getItem('workout_sound_v1')") == "off"
    before = len(_notes(page))
    # The finished rest moves on to the next set by itself
    expect(_arena(page)).to_have_attribute("data-phase", "set", timeout=10_000)
    page.locator("#arena-done-btn").click()
    assert _after_set(page) == "rest"
    assert len(_notes(page)) == before

    # Turning the sound back on (from the set screen, where the toggle lives) confirms itself audibly
    _rest_then_next(page)
    page.locator("#arena-sound-btn").click()
    assert _notes(page)[before:] == [660, 880]


def test_hold_countdown_ticks_before_the_end_chord(page):
    page.context.add_init_script(FAKE_AUDIO)
    page.reload()
    _start_path(page, "hspu")
    page.locator("#arena-hold-btn").click()
    assert _notes(page) == [660], "a hold announces its start"
    # Shorten the 30 s hold to its last seconds and let it run out on its own
    page.evaluate("() => { holdStartedAt = Date.now() - 27500; }")
    assert _after_set(page) == "rest"
    notes = _notes(page)
    assert notes[1:4] == [880, 880, 880], notes
    assert notes[4:7] == [660, 660, 990], notes
    assert len(notes) == 7, "the set cue stays silent after a hold — the end chord already said it"


def test_training_starts_only_when_start_is_pressed_after_the_warmup(page):
    page.locator('[data-start-path="muscle_up"]').first.click()
    expect(_arena(page)).to_have_attribute("data-phase", "warmup")

    # Ticking every warm-up item and pressing "warmed up" leads to the ready screen, not a set
    items = page.locator("#warmup-list .warmup-item")
    for i in range(items.count()):
        items.nth(i).click()
    page.get_by_role("button", name="מחומם — לזירה").click()
    expect(_arena(page)).to_have_attribute("data-phase", "ready")
    expect(page.locator("#ready-warmup-note")).to_be_visible()
    expect(page.locator("#ready-first-title")).not_to_be_empty()
    expect(_set_panel(page)).not_to_be_visible()

    # A refresh keeps the athlete on the ready screen
    page.reload()
    expect(_arena(page)).to_have_attribute("data-phase", "ready")

    # Back to the warm-up is possible; the ticks are kept
    page.get_by_role("button", name="חזרה לחימום").click()
    expect(_arena(page)).to_have_attribute("data-phase", "warmup")
    expect(page.locator("#warmup-list .warmup-item.is-done")).to_have_count(items.count())
    page.get_by_role("button", name="מחומם — לזירה").click()
    expect(_arena(page)).to_have_attribute("data-phase", "ready")

    # Only the start button opens the first set
    page.get_by_role("button", name="התחל אימון", exact=True).click()
    expect(_arena(page)).to_have_attribute("data-phase", "set")
    expect(_set_panel(page)).to_have_attribute("data-state", "active")


def test_arena_rest_shows_spanish_card(page, live_server, db_conn):
    """A 90 s rest carries one Spanish card: reveal, grade, one review row; the toggle silences it."""
    from datetime import datetime, timedelta

    yosef = db_conn.execute("SELECT id FROM users WHERE name = 'Yosef'").fetchone()["id"]
    db_conn.execute("DELETE FROM spanish_reviews")
    # One sentence met earlier today, so the rest opens on a recall card (due now)
    db_conn.execute(
        "INSERT INTO spanish_reviews (user_id, item_id, reviewed_at, grade, mode, context) "
        "VALUES (?, 'basics-001', ?, 2, 'intro', 'study')",
        (yosef, (datetime.now() - timedelta(minutes=5)).replace(microsecond=0).isoformat()),
    )
    db_conn.commit()
    try:
        page.goto(f"{live_server}/workouts")

        # The decision helpers, as pure functions
        assert page.evaluate("() => [30, 44, 45, 90, 119, 120, 180].map(s => Spanish.cardsForRest(s))") == [0, 0, 1, 1, 1, 2, 2]
        assert page.evaluate("() => Spanish.cardsForRest(90, false)") == 0
        assert page.evaluate("() => [null, 'on', 'off'].map(v => Spanish.readEnabled(v))") == [True, True, False]
        assert page.evaluate("() => Spanish.gradeFromSpeech('donde esta el bano', '¿Dónde está el baño?')") == 2
        assert page.evaluate("() => Spanish.gradeFromSpeech('el baño', '¿Dónde está el baño?')") == 1

        _start_path(page, "muscle_up")
        page.locator("#arena-done-btn").click()
        assert _after_set(page) == "rest"

        card = page.locator("#rest-spanish")
        expect(card).to_be_visible()
        expect(card).to_contain_text("מילים בכיס")
        expect(card.locator(".sp-card")).to_have_attribute("data-mode", "recall")
        expect(card).to_contain_text("איפה השירותים?")
        expect(card).to_contain_text("תגיד את זה בספרדית")
        card.get_by_role("button", name="הצג", exact=True).click()
        expect(card.locator(".sp-es mark")).to_have_text("baño")
        card.get_by_role("button", name="טוב", exact=True).click()
        expect(card).to_contain_text("נשמר")

        deadline = time.time() + 5
        rows = []
        while time.time() < deadline:
            rows = db_conn.execute(
                "SELECT item_id, grade, mode, context FROM spanish_reviews WHERE mode = 'recall'").fetchall()
            if rows:
                break
            time.sleep(0.1)
        assert [tuple(r) for r in rows] == [("basics-001", 2, "recall", "rest")]

        _rest_then_next(page)
        expect(card).to_be_hidden()

        # Switched off: the next rest has no card, and the choice persists
        page.locator("#arena-spanish-btn").click()
        expect(page.locator("#arena-spanish-btn")).to_have_attribute("aria-pressed", "false")
        expect(page.locator("#arena-spanish-btn")).to_contain_text("ספרדית: כבוי")
        page.locator("#arena-done-btn").click()
        assert _after_set(page) == "rest"
        expect(card).to_be_hidden()
        assert page.evaluate("() => localStorage.getItem('workout_spanish_v1')") == "off"
    finally:
        db_conn.execute("DELETE FROM spanish_reviews")
        db_conn.commit()
