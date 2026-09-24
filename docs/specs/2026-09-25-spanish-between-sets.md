# ספרדית בין סטים — spanish-between-sets

**Date:** 2026-09-25 · **Module:** workouts · **Who:** anyone who trains (Yosef first; Karina and Yonatan get their own progress)

## In one line
Every rest in the arena becomes one spaced-repetition rep of a real Spanish sentence, spoken out loud and graded, and the same queue is available outside the gym as a three-minute review, so the words survive between trainings.

## The signature
The rest timer is the study timer. A session has about ten rests of 60–180 seconds: that is a 15–25 minute study slot, three times a week, that already exists and is otherwise dead. "Words in your pocket" is earned exactly like a conquered station: computed from the review history, never marked by hand.

## Why this is not lame (design principles the implementation must keep)
1. **Sentences, never bare words.** Every card is a short natural sentence (3–9 words) with one target word highlighted. The same word appears in 2–3 different sentences across the deck, so it is met in context more than once.
2. **Retrieval, not recognition.** A recall card shows the Hebrew and asks the learner to say the Spanish out loud before revealing. Grading is a self-grade (שוב / קשה / טוב / קל). No multiple choice.
3. **The first meeting is input.** A new item first appears as an *intro* card (Spanish + Hebrew + audio, one button "הבנתי"), and comes back later in the same session as a recall card.
4. **Audio on every card.** Browser `speechSynthesis` with a Spanish voice, auto-played on intro and on reveal, replayable, with a slow replay (rate 0.7).
5. **Real spacing across days.** An SM-2-style stage ladder computed from the review rows; lapses go back to the start. Due items always come before new ones; new items are capped per day so the review load stays sane.
6. **Speak-to-check when the phone can.** If the browser has Spanish speech recognition, a mic button listens and pre-selects a grade; otherwise the mic button is not shown. It never blocks grading.
7. **Not gated by the gym.** A `#spanish` view on the workouts page runs the same queue as a short study session, with stats. The gym seeds the habit; the view keeps it alive.
8. **Per person.** Reviews are keyed by `users.id`; each trainer has their own queue and stats.

## Framings considered
- A (straight): a flashcard app inside the app, words with pictures, tap-to-flip — lost because it competes with Duolingo and loses, and nobody opens a second app in the gym.
- B (house style): the rest timer as the study timer, sentences spoken out loud, progress earned like stations — chosen.
- C (subtraction): only a "word of the day" on the home view — lost because one exposure with no retrieval teaches nothing.

## Behaviour

### The deck
`app/frontend/static/spanish/deck.json`, checked in, loaded by the backend (cached by file mtime) and by the page. Shape:

```json
{
  "version": 1,
  "themes": [{"key": "basics", "title": "בסיס ונימוס", "order": 1}, ...],
  "items": [
    {"id": "basics-001", "theme": "basics", "es": "¿Dónde está el baño?", "he": "איפה השירותים?",
     "target_es": "baño", "target_he": "שירותים", "lemma": "baño", "note": ""}
  ]
}
```

- 12 themes in this order: `basics` (בסיס ונימוס), `numbers_time` (מספרים וזמן), `restaurant` (במסעדה), `getting_around` (בדרך: מונית, שדה תעופה, כיוונים), `hotel` (במלון), `shopping_money` (קניות וכסף), `small_talk` (שיחת חולין: להכיר, מאיפה אתה, אני מישראל), `couple` (זוגיות ורגשות: te quiero, mi esposa, luna de miel), `health_emergency` (בריאות וחירום), `daily_life` (בית ויומיום), `work` (עבודה), `wedding_family` (חתונה ומשפחה).
- **25 sentences per theme, 300 total.** Sentences are short (3–9 words), natural, in neutral Latin-American Spanish (`tú` for informal, `ustedes` never `vosotros`), present tense first, past/future only in the later themes. Every `target_es` must appear verbatim in `es` (a test enforces it). Roughly 400+ distinct lemmas overall; a lemma should recur in 2–3 sentences. The Hebrew is natural spoken Hebrew, not a literal gloss. `note` is optional, one short line in Hebrew (a false friend, a gender note, a pronunciation hint like "ll נשמע כמו י").
- Ids are stable strings `<theme>-<nnn>`; they are what the reviews table references, so they never change once shipped.

### Spacing engine (`services/spanish.py`, pure functions, unit-tested)
- Stage ladder intervals in days: `[0, 1, 3, 7, 14, 30, 60, 120]` (stage 0–7).
- An item with no reviews is **new**. Its first card is `intro`; recording an intro puts it at stage 0, due now.
- Recall grades: `0 שוב` → stage 0, due now. `1 קשה` → stage unchanged (minimum 1), due = now + interval[stage]. `2 טוב` → stage + 1. `3 קל` → stage + 2. Max stage 7. Due = review time + interval[new stage] days (at day granularity: due when `today >= due_date`).
- State per item is computed by replaying its reviews in `reviewed_at` order. Nothing about stage or due is stored.
- **Queue** for a user at `now`: (1) due recall items, oldest due first; (2) new items in deck order, limited to `new_cap - intros already recorded today`. `new_cap` is 8 by default; the study view may pass `new_cap=15`. Items introduced this session (stage 0, due now) are legitimately in (1).
- **Stats**: `in_pocket` = items at stage ≥ 3 (interval ≥ 7 days), `learning` = stage 1–2, `mastered` = stage ≥ 6, `due_today`, `new_today_left`, `review_days_streak` (consecutive days ending today or yesterday with ≥ 1 review), `per_theme` = `{key: {"total", "in_pocket"}}`.

### In the arena (rest panel)
A new card at the top of `.rest-foot`, before "הבא בתור": `.rest-card.rest-spanish`.

- Shown only when the rest is ≥ 45 seconds and the toggle is on. Rest ≥ 120 s may show a second card after the first is graded.
- Eyebrow: `ספרדית · {{ in_pocket }} מילים בכיס`, and a small toggle button (`ספרדית: פועל / כבוי`) next to the existing sound toggle, persisted in `localStorage` (`workout_spanish_v1`, default on).
- **Intro card:** the Spanish sentence large, `dir="ltr"`, target word emphasised; Hebrew underneath; 🔊 button (auto-plays once on show); button `הבנתי` → records `{mode: "intro", grade: 2}`.
- **Recall card:** the Hebrew prompt large; hint line `תגיד את זה בספרדית`; 🎤 button when speech recognition exists; button `הצג`. After reveal: the Spanish sentence with the target emphasised, audio auto-plays, then four grade buttons in one row: `שוב · קשה · טוב · קל`. Tapping one records the review and, if time remains and this is the first card, may show the next.
- The `theme` title shows small under the sentence (`במסעדה`), and the `note` if any.
- If the rest ends before grading, nothing is recorded; the item stays where it was.
- Cards come from `client_data.spanish.queue` (first 12 items rendered into the page) so a rest never waits on the network; when fewer than 3 remain, the JS fetches more from the queue endpoint. Reviews are posted with `fetch(..., {keepalive: true})`; on failure they are kept in `localStorage` (`workout_spanish_pending_v1`) and flushed on the next page load.
- The existing coach tip card stays; the Spanish card sits above it.

### Speech
- TTS: pick a voice whose `lang` starts with `es`, preferring `es-ES` then `es-MX`; voices may arrive asynchronously (`onvoiceschanged`). If none exists, hide the 🔊 buttons; everything else works.
- Recognition: `window.SpeechRecognition || window.webkitSpeechRecognition`, `lang = "es-ES"`, `interimResults = false`. Normalise both strings (lowercase, strip accents and punctuation), compare by token overlap: Jaccard ≥ 0.6 pre-selects `טוב` (highlighted, not submitted), lower pre-selects `קשה`, and the heard text is shown under the card in small type. Any error (no permission, no result) simply leaves the buttons unselected. Never send audio anywhere.

### The `#spanish` view (outside the gym)
A new `.wk-view[data-view="spanish"]` on the workouts page, reachable from a `ספרדית` link on the home view (next to the mission cards, styled like the existing `.wk-mission-link`) and a card on the profile view.

- Header: `ספרדית` with the stats row: `מילים בכיס · בדרך · לחזרה היום · רצף ימים`.
- A "study session" of up to 15 cards using the same card component as the arena, one after another, with a progress dots strip; ends with a small summary (`X חזרות · Y מילים חדשות`). Button `עוד חדשות` requests a queue with `new_cap=15`.
- Theme progress list: each theme with `in_pocket / total` and a thin bar.
- Empty queue: `אין מה לחזור עליו עכשיו — המילים הבאות יחכו במנוחה הבאה`.

### Profile view
A small card `ספרדית: {{ in_pocket }} מילים בכיס` linking to `#spanish`. One new achievement in the existing achievements list: `id "spanish_50"`, title `50 מילים בכיס`, unlocked when `in_pocket >= 50` (achievements are computed in `compute_gamification`; pass the Spanish stats in, or compute alongside, whichever is cleaner and keeps the pure-function style).

### Mobile and desktop
The workouts page is one mobile-first layout for both; no other page changes.

## Data

New table, inline idempotent migration in `initialise_database()` (`db.py`), following `.claude/skills/db-migration/SKILL.md`:

```sql
CREATE TABLE IF NOT EXISTS spanish_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    item_id TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,        -- ISO datetime, local time
    grade INTEGER NOT NULL,           -- 0..3
    mode TEXT NOT NULL,               -- 'intro' | 'recall'
    context TEXT NOT NULL DEFAULT 'rest',  -- 'rest' | 'study'
    FOREIGN KEY (user_id) REFERENCES users (id)
);
CREATE INDEX IF NOT EXISTS idx_spanish_reviews_user_item ON spanish_reviews (user_id, item_id);
```

Derived, never stored: stage, due date, in_pocket, streak, per-theme progress. The deck is a static file, not a table.

## API

New router `app/backend/app/api/spanish.py`, `prefix="/api/workouts/spanish"` (under the workouts prefix so `services/access.py` rules apply unchanged: Yonatan allowed, Tsahala 403), registered in `main.py` next to `workouts_api`. User resolved the way `api/workouts.py` does it.

- `GET /api/workouts/spanish/queue?limit=15&new_cap=8` → `{"items": [{"id","theme","theme_title","es","he","target_es","target_he","note","mode","stage"}], "stats": {...}}`
- `POST /api/workouts/spanish/reviews` body `{"item_id","grade","mode","context"}` (Pydantic in `schemas/spanish.py`: grade 0–3, mode/context enums, item_id must exist in the deck → 422 otherwise) → 201 `{"item_id","stage","due_on","stats": {...}}`
- `GET /api/workouts/spanish/stats` → the stats object.

## Files to touch
- `app/backend/app/db.py` — table + index migration.
- `app/backend/app/services/spanish.py` — new: `load_deck()`, `item_states(reviews)`, `build_queue(...)`, `stats(...)`, all pure over rows/dicts except two thin DB readers.
- `app/backend/app/schemas/spanish.py` — new.
- `app/backend/app/api/spanish.py` — new router; `main.py` registration.
- `app/backend/app/routes/workouts.py` — `client_data["spanish"]` (initial queue + stats), template context `spanish` for the profile card and the view, the achievement.
- `app/frontend/templates/pages/workout.html` — rest card, `#spanish` view, profile card, home link, toggle button.
- `app/frontend/static/js/spanish.js` — new: card component, TTS, recognition, queue cache, pending-review flush; exposes `window.Spanish = {onRestStart(seconds), onRestEnd(), mountStudy(el)}`.
- `app/frontend/static/js/workout.js` — call `Spanish.onRestStart` / `onRestEnd` from the existing rest start/stop functions (around `startRestTimer` / `stopRestTimer` / `skipRestTimer`), and wire the `#spanish` hash view into `showView`.
- `app/frontend/static/css/workout.css` — `.rest-spanish`, grade buttons, the study view.
- `app/frontend/static/spanish/deck.json` — new, 300 items.
- `tests/test_spanish_deck.py`, `tests/test_spanish_engine.py`, `tests/test_spanish_api_e2e.py` — new.

## Acceptance criteria
1. `deck.json` has 12 themes in the specified order, exactly 300 items, 25 per theme, unique ids of the form `<theme>-<nnn>`, and every item's `target_es` occurs in its `es`; no item's `es` contains "vosotros".
2. Engine: replaying intro → good → good → good on 2026-01-01 with the stage ladder yields stage 3 and `due_on == 2026-01-08`; a subsequent `שוב` returns stage 0 due now; `קשה` at stage 2 keeps stage 2 and due = today + 3 days; `קל` at stage 1 gives stage 3.
3. Queue: a fresh user gets `intro` cards in deck order, at most `new_cap`; after 8 intros today the queue has no new items unless `new_cap=15`; due items precede new items; an item graded 3 today is absent from today's queue.
4. Stats: `in_pocket` counts stage ≥ 3 only; `review_days_streak` counts consecutive days ending today or yesterday.
5. Reviews are per user: reviews recorded for Yonatan do not change Yosef's queue or stats.
6. API: `POST` with an unknown `item_id` or grade 4 → 422; a valid post → 201 with the new stage; Tsahala gets 403 on `/api/workouts/spanish/queue` and Yonatan gets 200 (use the `can_access_path` unit-test style from `tests/test_workouts_access_e2e.py`).
7. The workouts page HTML contains the rest card markup (`rest-spanish`), the `data-view="spanish"` section, the profile card, and `client_data.spanish.queue` with items for a fresh user.
8. `spanish.js` shows no card for a rest under 45 s, one card at 90 s, and respects the localStorage toggle (unit-testable by exporting the decision helpers as pure functions on `window.Spanish`; if the Playwright browser tests in `tests/test_workouts_arena_browser.py` run in the pinned venv, add one browser test that completes a set, sees the Spanish card during rest, reveals, grades, and finds one row in `spanish_reviews`).
9. Achievement `spanish_50` appears in the achievements list, locked for a fresh user.
10. Full test suite: no new failures beyond the pre-existing ones.

## Tests to add
- `test_deck_shape_and_targets`
- `test_stage_ladder_and_due_dates`
- `test_lapse_resets_and_hard_holds`
- `test_queue_orders_due_before_new_and_caps_new`
- `test_stats_in_pocket_and_streak`
- `test_reviews_are_per_user`
- `test_review_post_validation_and_stage`
- `test_spanish_routes_follow_workouts_access`
- `test_workout_page_ships_spanish_queue_and_view`
- `test_arena_rest_shows_spanish_card` (browser, if the infra runs)

## Out of scope
Pictures, typing answers, grammar lessons, a second language, XP for reviews, notifications, editing the deck from the UI, syncing progress between people.

## Open questions
None. The user approved "go ahead"; the theme list is the designer's call and can be tuned later without touching the engine because ids are per theme.
