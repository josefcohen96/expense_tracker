# הבוס: החתונה — wedding-boss

**Date:** 2026-09-25 · **Module:** workouts · **Who:** Yosef only

## In one line
On Yosef's workout home, the wedding date becomes the deadline of the game: how many trainings he can still fit before the wedding at his own pace, and where each quest path will stand on the wedding day.

## The signature
No other tracker knows when its user gets married. The app already holds the wedding date (`wedding_settings.wedding_date`, read via `services/wedding_plan.get_wedding_date`) and a countdown; the arena gets to use it as its final boss. Nothing new is stored; everything follows from the wedding date plus Yosef's workout history.

## Framings considered
- A (straight): a "goal date" setting on the profile with a generic countdown — lost because the date already exists, and a setting is a tap nobody will make.
- B (house style): the wedding as the boss, trainings-left computed from real cadence, per-path forecast — chosen.
- C (subtraction): only a "N days to the wedding" badge in the header — lost because a number without a forecast does not change what he does today.

## Behaviour

Only when **all** hold: the viewer is Yosef (`normalise_username(_session_user(request)["username"]) == USER_YOSEF` from `services/access.py`), a wedding date exists, and it is today or in the future. Otherwise nothing renders and nothing is added to the template context. Karina and Yonatan never see any of this, not even an empty container.

**Home view (`data-view="home"`), above the first mission card:** a boss banner (`.wk-boss`):

- Eyebrow: `הבוס הסופי`
- Title: `החתונה בעוד {{ days }} ימים` (use `hebrew_dates` helpers for the wording; 1 day → `מחר`, 0 → `היום`).
- Line: `עוד ~{{ trainings_left }} אימונים בקצב שלך ({{ per_week }} בשבוע)`; when the pace is assumed rather than measured: `עוד ~{{ n }} אימונים בקצב של 2 בשבוע`.
- A thin progress bar: trainings done in the last 28 days vs. trainings left, purely decorative (aria-hidden), tinted with the wedding module's rose/pink rather than the path tint, so it reads as "wedding", not "path".

**Inside each mission card (`.wk-mission`), under `.wk-mission-sub`:** one forecast line per path (`.wk-mission-boss`), ring emoji 💍 first:

- Path finishes before the wedding: `תסיים את המסלול לפני החתונה` 
- Otherwise: `עד החתונה תגיע לתחנה {{ n }} · {{ station hebrew }}`
- Path already complete: no line.

Mobile and desktop: the workouts page is a single mobile-first layout with no separate desktop variant, so the same markup serves both. No other page changes.

## Data

All derived in `routes/workouts.py`, no schema change:

```
def wedding_boss(history, paths, wedding_date, today) -> Optional[dict]
```

- `days_left = (wedding_date - today).days`; return `None` if `< 0`.
- Cadence: distinct workout days in the last 56 days (8 weeks) from `history`, `per_week = round(days / 8, 1)`. If fewer than 3 distinct days in that window, `per_week = 2.0` and `assumed = True`.
- `trainings_left = max(0, round(per_week * days_left / 7))`.
- `recent_28 = distinct workout days in the last 28 days`.
- Per path forecast: walk the unconquered stations in order, consuming `remaining` (the existing `STATION_SESSIONS_TO_CONQUER - in_range`) from a budget of `trainings_left`; the station where the budget runs out is the one reached (`number`, `hebrew`); if the budget covers every station, `finishes = True`. Skip locked paths and complete paths.
- Return: `{"days_left", "days_label", "per_week", "assumed", "trainings_left", "recent_28", "paths": {key: {"finishes": bool, "station_number": int|None, "station_hebrew": str|None}}}`.

## API
None. The page route passes `wedding_boss` in the template context (and `None` for everyone but Yosef).

## Files to touch
- `app/backend/app/routes/workouts.py` — `wedding_boss()` + call in `workout_page` gated on the viewer; import `get_wedding_date` from `services/wedding_plan` and `USER_YOSEF`, `normalise_username` from `services/access`.
- `app/frontend/templates/pages/workout.html` — banner above the mission cards; forecast line inside each mission card.
- `app/frontend/static/css/workout.css` — `.wk-boss`, `.wk-boss-bar`, `.wk-mission-boss` in the existing visual language (rounded card, subtle sheen, rose tint).
- `tests/test_workouts_wedding_boss_e2e.py` — new.

## Acceptance criteria
1. With a wedding date 30 days ahead and Yosef as the viewer, GET `/workouts` contains `הבוס הסופי` and `החתונה בעוד 30 ימים`.
2. Karina and Yonatan as viewers never get `הבוס הסופי` in the page, with the same wedding date set. (Use the `authed` fixture pattern from `tests/test_workouts_access_e2e.py` to log in as each; or, if simpler, call `wedding_boss` gating through the page with a session user injected the way that test does.)
3. No wedding date, or a wedding date in the past: no banner for Yosef.
4. `wedding_boss()` unit: 8 distinct workout days in the last 56 days and 28 days left → `per_week == 1.0`, `trainings_left == 4`, `assumed is False`; 2 workout days → `per_week == 2.0`, `assumed is True`.
5. Forecast unit: a path with stations remaining `[2, 5, 5]` and `trainings_left == 6` reaches station 2 (index 1) with `finishes False`; `trainings_left == 12` → `finishes True`.
6. The mission card of a path that will not finish shows `עד החתונה תגיע לתחנה`; a complete path shows no forecast line.
7. Full test suite: no new failures beyond the pre-existing ones.

## Tests to add
- `test_wedding_boss_pace_measured_and_assumed`
- `test_wedding_boss_forecast_walks_remaining_stations`
- `test_yosef_sees_the_boss_banner`
- `test_household_and_yonatan_do_not_see_the_boss`
- `test_no_banner_without_or_after_wedding_date`

## Out of scope
Notifications, arena/reward-screen mentions, anything for Karina, storing a goal, changing the wedding date from the workouts page.

## Open questions
None.
