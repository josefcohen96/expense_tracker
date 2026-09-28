# קריאה לזירה — arena-push

**Date:** 2026-09-28 · **Module:** workouts · **Who:** anyone who trains (Yosef, Karina, Yonatan), each on their own phone

## In one line
Real lock-screen push notifications from the arena: a morning call with today's mission, and an evening nudge only on a day you have not trained yet, sent through Web Push to every phone where the trainee turned them on.

## The signature
**The evening notification knows you already trained.** It is never a fixed alarm: on a day you trained there is no evening push at all (silence is the reward). On a day you did not, it names what is at stake, e.g. `🔥 הרצף של 12 ימים נגמר בחצות` when the streak is alive only thanks to yesterday, or a small way back in (`15 דקות בסלון מספיקות להיום`) when there is no streak. The morning push is the same mission card the home view shows: its path and station, or the rest-day note when `plan_today()` recommends rest.

## Framings considered
- A (straight): a settings page with a daily reminder at a time you choose, same text every day. Lost because it nags on the days you trained and says nothing a phone alarm doesn't.
- B (house style): the texts come from what the arena already knows (`plan_today`, current streak, `streak_at_risk`), the evening push is skipped when you trained, and one toggle turns everything on. **Chosen.**
- C (subtraction): no push, just rely on היום. Lost because the user explicitly wants lock-screen notifications. היום only helps once the app is already open.

Calendar: fixed, predictable times (07:30 / 20:30). Messaging app: one line and a tap that opens the right screen. Board game: the evening push reads like "your turn, the streak is on the table". Bank statement: nothing.

## Behaviour

### Turning it on (the `#profile` view, mobile and desktop are the same page)
A new card under the stats row (`wk-stats`) and above the Spanish card:
- Title `🔔 קריאה לזירה`, sub-line `בוקר 07:30 · ערב 20:30, רק אם עוד לא התאמנת`.
- The action button depends on state (all decided in JS):
  - Push not supported by the browser, or the server has no VAPID key (`enabled: false`): card hidden entirely.
  - iPhone/iPad not running as an installed app (`navigator.standalone !== true` and not `display-mode: standalone`): no button; the sub-line becomes `באייפון: שתף ← "הוסף למסך הבית", ואז פותחים את האפליקציה משם`.
  - Permission `denied`: no button, sub-line `ההתראות חסומות בהגדרות הדפדפן`.
  - Not subscribed on this device: button `להפעיל`. Tap → `Notification.requestPermission()` → `pushManager.subscribe({userVisibleOnly: true, applicationServerKey})` → `POST /api/workouts/push/subscribe`. On success: toast `ההתראות פועלות במכשיר הזה` and the card switches to the subscribed state.
  - Subscribed on this device: two small buttons, `לשלוח בדיקה` (POST `/push/test`, toast `נשלחה התראת בדיקה`) and `לכבות` (unsubscribe in the browser + `DELETE /push/subscribe`, toast `ההתראות כובו במכשיר הזה`, with an undo action (`AppToast(msg, 'בטל', resubscribe)`), no confirm dialog).
- Errors: toast `לא הצלחנו להפעיל התראות` and log to the console.

### The notifications (server-side, Asia/Jerusalem)
Each is sent to every subscription of each user who has one.

**Morning, 07:30.** Derived from the same inputs as `workout_page` (history, gamification, paths, `plan_today`):
- Rest-day recommendation (`plan_today` returned the recovery note, i.e. streak ≥ `RECOVERY_STREAK_DAYS`): title `☀️ בוקר טוב — יום מנוחה`, body `{n} ימים ברצף. היום נחים, והכוח נבנה.`
- Otherwise: title `☀️ המשימה של היום`, body `{path icon} {path name} · {next unconquered station Hebrew name}` (if the path has none left, just the path). If `streak_at_risk`, append ` · הרצף ({n}) מחכה לך`.
- URL: `/workouts#home`.

**Evening, 20:30.** Skipped entirely when the user has a workout row dated today.
- Streak at risk (current streak > 0, trained yesterday, not today): title `🔥 הרצף בסכנה`, body `הרצף של {n} ימים נגמר בחצות. אימון אחד קצר שומר עליו.` (n = 1 → `הרצף של יום אחד`).
- No live streak: title `🏠 עוד לא מאוחר`, body `15 דקות בסלון מספיקות להיום.`. URL `/workouts#house`.
- URL for the streak case: `/workouts#home`.

**Test** (`/push/test`): title `🔔 קריאה לזירה`, body `ההתראות עובדות. נתראה בזירה.`, URL `/workouts#profile`.

All pushes use `tag` = `arena-morning` / `arena-evening` / `arena-test` so a repeat replaces instead of stacking, `icon` = `/static/icons/icon-192.png`, `lang: he`, `dir: rtl`.

### Service worker
- `push` event: parse JSON `{title, body, url, tag}` and `showNotification`.
- `notificationclick`: close the notification, focus an open client already on `/workouts` and navigate it to `url`, else `clients.openWindow(url)`.
- Must not break the existing fetch caching logic. Bump the cache version constants.

### Manifest
`"display": "standalone"` (needed for iOS web push; also removes the address bar when launched from the home screen). Add `"id": "/"`.

## Data
New table, created with the db-migration pattern (`CREATE TABLE IF NOT EXISTS` in `initialise_database()`):

```sql
push_subscriptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  endpoint TEXT NOT NULL UNIQUE,
  p256dh TEXT NOT NULL,
  auth TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
)
```
Subscribing with an endpoint that exists again re-points it to the current user (upsert on `endpoint`), so a shared phone follows whoever logged in last.

Idempotency: after a scheduled run completes, write `system_settings` key `push_sent:<kind>:<YYYY-MM-DD>` (kind = `morning` / `evening`). A run that finds its key already set sends nothing, so a restart inside the misfire window never double-sends. Nothing about content is stored; texts are derived at send time.

Dead subscriptions: a send that returns HTTP 404 or 410 deletes that row.

## API
New router `api/push.py`, prefix `/api/workouts/push` (inside `WORKOUTS_PREFIXES`, so every trainee including Yonatan can reach it; no `access.py` change). The user is resolved like `routes/workouts._resolve_user_id`.
- `GET /api/workouts/push/key` → `{"enabled": bool, "public_key": str | null}`. `enabled` is false when the VAPID env vars are missing.
- `POST /api/workouts/push/subscribe` body `{"endpoint": str, "keys": {"p256dh": str, "auth": str}}` (the browser's `subscription.toJSON()`) → `{"ok": true}`. 422 on a missing field. 503 when disabled.
- `DELETE /api/workouts/push/subscribe` body `{"endpoint": str}` → `{"ok": true}` (only deletes the caller's own row; unknown endpoint is still ok).
- `POST /api/workouts/push/test` → `{"sent": int}`, the number of the caller's subscriptions that accepted it. 503 when disabled.

## Env
- `VAPID_PUBLIC_KEY`: base64url uncompressed P-256 public key (what `applicationServerKey` takes).
- `VAPID_PRIVATE_KEY`: base64url raw private key (the format `pywebpush`/`py_vapid` accept).
- `VAPID_SUBJECT`: optional, a `mailto:` contact for the push services; default `mailto:admin@example.com` (set a real one in Railway).
- If either key is missing, the feature is off: no scheduler jobs, `enabled: false`, card hidden. No crash.
- New script `tools/generate_vapid_keys.py` prints the two values ready to paste into Railway (uses `cryptography`, which `pywebpush` brings).

## Dependency
`pywebpush` (pinned, `pywebpush==2.0.3` or whatever latest 2.x installs cleanly) added to `requirements.txt`. The user approved this exception to "no new dependencies" in conversation. Import it lazily inside the sender so tests and the app still import if it is missing.

## Files to touch
- `requirements.txt`: add `pywebpush`.
- `app/backend/app/db.py`: `push_subscriptions` table.
- `app/backend/app/services/push_service.py` (new): `vapid_config()`, `is_enabled()`, `save_subscription`, `delete_subscription`, `send_to_user(conn, user_id, payload) -> int` (handles 404/410 cleanup), `morning_message(conn, user_id, today)` / `evening_message(conn, user_id, today)` returning a payload dict or `None`, `run_daily(kind, today=None)` (idempotent via `system_settings`). Import helpers from `routes/workouts.py` lazily inside functions to avoid import cycles.
- `app/backend/app/api/push.py` (new): the four routes.
- `app/backend/app/main.py`: include the router.
- `app/backend/app/services/cron_service.py`: two `CronTrigger` jobs (07:30, 20:30, `timezone="Asia/Jerusalem"`), added only when `push_service.is_enabled()`, `coalesce=True`, `max_instances=1`, `misfire_grace_time=1800`.
- `app/frontend/static/js/sw.js`: `push` + `notificationclick` handlers, cache version bump.
- `app/frontend/static/manifest.json`: standalone + id.
- `app/frontend/templates/pages/workout.html`: the profile card (markup only, `hidden` by default).
- `app/frontend/static/js/workout.js` (or a new small `static/js/components/arena-push.js` loaded by the page, whichever is cleaner): the card logic.
- `app/frontend/static/css/workout.css`: card styles reusing existing `wk-card` look.
- `tools/generate_vapid_keys.py` (new).
- `CLAUDE.md`: env var rows, table, the push service line.

## Acceptance criteria
1. With no VAPID env vars, `GET /api/workouts/push/key` returns `{"enabled": false, "public_key": null}` and `POST /push/test` returns 503. The app starts and no push jobs are scheduled.
2. With keys set, `GET /push/key` returns `enabled: true` and the public key.
3. `POST /push/subscribe` stores one row for the current user; posting the same endpoint again does not add a second row.
4. `DELETE /push/subscribe` removes the row; a second delete still returns 200.
5. `evening_message` returns `None` when the user has a workout dated today.
6. `evening_message` returns the streak text with the right day count when the user trained yesterday and not today (current streak ≥ 1).
7. `evening_message` returns the `#house` payload when the user has no live streak.
8. `morning_message` returns the rest-day payload when the user trained on the last `RECOVERY_STREAK_DAYS` days, and the mission payload (containing the recommended path's name) otherwise.
9. `send_to_user` deletes a subscription whose send raises a WebPush error with status 404 or 410, and keeps it on another error.
10. `run_daily("morning", today)` twice on the same day sends only once (second call sends 0).
11. `/sw.js` still serves as JavaScript and contains `addEventListener('push'` and `notificationclick`.
12. `manifest.json` has `"display": "standalone"`.
13. The profile view renders the card container (hidden by default) and the page still returns 200 for a workouts-only login.
14. The full existing test suite passes as before.

## Tests to add
`tests/test_arena_push_e2e.py`:
- `test_key_disabled_without_env`, `test_key_enabled_with_env` (monkeypatch env).
- `test_subscribe_upserts_by_endpoint`, `test_unsubscribe_idempotent`.
- `test_evening_skipped_when_trained_today`, `test_evening_streak_at_risk_text`, `test_evening_no_streak_points_to_house`.
- `test_morning_rest_day`, `test_morning_mission_names_path`.
- `test_dead_subscription_removed` (monkeypatch the low-level send to raise with a 410 response).
- `test_run_daily_idempotent` (monkeypatch send; count calls).
- `test_sw_has_push_handlers`, `test_manifest_standalone`.
Use a dedicated test user id or clean up the workout rows each test inserts, so other tests' history is unaffected.

## Out of scope
- Choosing custom times per user (fixed 07:30 / 20:30 for now; constants in `push_service`).
- Separate morning/evening toggles.
- Push for finances or the wedding.
- Notification action buttons, badges, or images.
- Any change to desktop layout other than the new profile card (the workouts page is shared across sizes already).

## Open questions
None. Times are constants and easy to change later.
