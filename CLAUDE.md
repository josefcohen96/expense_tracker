# Project Overview — המנביטים (Expense Tracker, Wedding Planner, Renovation, Arena)

## What This App Is

A household web app built for two specific people, **Yosef** and **Karina**, with two more single-module logins
(**Tsahala** for the renovation, **Yonatan** for the workouts). Five areas behind one login:

| Module | URL prefix | What it is |
|---|---|---|
| היום (today) | `/` | The phone's landing screen: what needs doing now across the modules, plus this month's money. |
| כספים (finances) | `/finances`, `/api/transactions`… | Income/expense ledger, recurring charges, statistics, backups, Max card-statement import. |
| חתונה (wedding) | `/wedding`, `/api/wedding` | Vendors, guests + RSVP links, seating, lodging, tasks, budget, notes, ideas, timeline, milestones, overseas orders. |
| שיפוץ (renovation) | `/renovation`, `/api/renovation` | Rooms, tasks, ideas, supplies, before/after journal. Its own look and navigation. |
| הזירה (workouts) | `/workouts`, `/api/workouts` | Calisthenics tracker built as a game, with Spanish flash-cards between sets and Web Push nudges. |

The UI is **Hebrew**; the code, identifiers and API surface are **English**. Deployed on **Railway** as a Docker
container; a server-rendered monolith with no client-side framework and no JS build step.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 (Dockerfile, CI); the local `.venv` is 3.13 |
| Web framework | FastAPI 0.136.3 + Uvicorn 0.29.0 — pinned: 0.137+ wraps included routers and hides `@public` routes (see `requirements.txt`) |
| Middleware/sessions | Starlette 1.7.0 (`TemplateResponse(request, name, ctx)` — the request-first form is mandatory) |
| Database | SQLite (raw `sqlite3`, no ORM) |
| Schema validation | Pydantic v2 |
| Templating | Jinja2 3.1.6, one shared environment (`templating.py`) |
| Background jobs | APScheduler 3.10.4 |
| Excel | OpenPyXL 3.1.5 (export, backups, card-statement import) |
| Web Push | pywebpush 2.5.0 (imported lazily) |
| Auth cookies | itsdangerous (signed cookies) |
| Frontend JS | Vanilla JS, no bundler. One file per page under `static/js/pages/`, shared pieces under `components/`, `core/`, `charts/` |
| Charts | Chart.js (vendor-bundled) |
| CSS | `main.css` (finances, wedding, shell), `renovation.css`, `workout.css` |
| PWA | Service worker `/sw.js`, `manifest.json`, icons (`layout/_icons.html`) |
| Dev tooling | ruff, pytest, Playwright (browser suites), pre-commit, GitHub Actions — `pyproject.toml`, `requirements-dev.txt` |

---

## Project Structure

```
expense_tracker/
├── app/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── main.py                  # App factory, middleware, router includes, startup
│   │   │   ├── auth.py                  # @public decorator + build_public_route_matchers()
│   │   │   ├── templating.py            # The one Jinja2Templates, template/static paths, wedding_header global
│   │   │   ├── recurrence.py            # Recurring-transaction materialisation engine
│   │   │   ├── seed_data.py             # Legacy seed helpers (not used at runtime)
│   │   │   ├── db/                      # Schema + inline migrations, one module per app module
│   │   │   │   ├── __init__.py          # DB_PATH, get_connection(), get_db_conn(), initialise_database()
│   │   │   │   ├── finance.py           # Core tables, finance migrations, default data (categories, users, accounts)
│   │   │   │   ├── wedding.py           # Wedding tables, migrations, default rooms, starter milestones
│   │   │   │   ├── renovation.py        # Renovation tables, migrations, starter rooms
│   │   │   │   └── workouts.py          # Arena tables: workouts, spanish_reviews, push_subscriptions
│   │   │   ├── api/                     # JSON endpoints
│   │   │   │   ├── transactions.py      # CRUD, duplicate, Excel export, card-statement import (preview/import/auto/undo)
│   │   │   │   ├── recurrences.py       # CRUD + apply-once; also system_router (/api/system/apply-recurring)
│   │   │   │   ├── statistics.py        # Aggregated stats + cache clear
│   │   │   │   ├── backup.py            # ZIP + Excel backups, restore
│   │   │   │   ├── wedding/             # Package, one module per feature; __init__ aggregates the 13 routers
│   │   │   │   │   ├── vendors.py  guests.py  rooms.py  tasks.py  budget.py  settings.py  files.py
│   │   │   │   │   └── notes.py  ideas.py  overseas.py  timeline.py  milestones.py  seating.py
│   │   │   │   ├── renovation.py        # Rooms, tasks, ideas, supplies, journal (+ photo upload); writes need an editor
│   │   │   │   ├── workouts.py          # Back-office CRUD: sessions + imported stations
│   │   │   │   ├── spanish.py           # /api/workouts/spanish: queue, stats, reviews
│   │   │   │   ├── push.py              # /api/workouts/push: key, subscribe, unsubscribe, test
│   │   │   │   └── today.py             # /api/today aggregate, /api/quick-add/options
│   │   │   ├── routes/                  # HTML pages (Jinja2)
│   │   │   │   ├── auth.py              # /login, /logout, the login rate limit
│   │   │   │   ├── home.py              # / (היום), /more, /sw.js
│   │   │   │   ├── finances.py          # /finances/* pages, /income + /recurrences inline forms
│   │   │   │   ├── wedding.py           # /wedding/* pages, public /invite/{token} RSVP pages
│   │   │   │   ├── renovation.py        # /renovation/* pages (own base template)
│   │   │   │   ├── workouts.py          # /workouts page, /workouts/admin, save + legacy import
│   │   │   │   ├── partials.py          # Inline-edit row fragments for transactions / income / recurrences (no prefix)
│   │   │   │   └── debug_logs.py        # /debug/logs, /debug/logs/auth, /debug/logs/errors
│   │   │   ├── schemas/                 # Pydantic models: transactions, recurrences, backup, wedding, workouts, spanish, push
│   │   │   ├── scripts/                 # One-off maintenance scripts (create_minimal_db.py, list_recurrences.py)
│   │   │   └── services/
│   │   │       ├── access.py            # Who may see / edit which module; path checks used by the middleware
│   │   │       ├── auth_middleware.py   # AuthMiddleware: session → signed cookie → /login; module access → redirect/403
│   │   │       ├── people.py            # Household (Yosef/Karina) + workout participants, colours, default accounts
│   │   │       ├── today.py             # היום queue across modules + month totals
│   │   │       ├── hebrew_dates.py      # Relative-date labels (באיחור ביומיים, בעוד 4 ימים)
│   │   │       ├── card_statement.py    # Max credit-card statement parsing, payer guess, duplicate detection, category learning
│   │   │       ├── wedding_plan.py      # Countdown, date-anchored milestones, headcount, committed money
│   │   │       ├── overseas.py          # הזמנות מחו״ל lanes, big-order cost + deadline (derived)
│   │   │       ├── uploads.py           # Shared upload rules: extension, size, magic bytes (vendor files, journal photos)
│   │   │       ├── spanish.py           # Spaced-repetition engine replayed from spanish_reviews; deck is a static file
│   │   │       ├── workouts/            # Arena logic (no re-exports in __init__)
│   │   │       │   ├── catalog.py       # Static content: paths/stations, exercises, tempos, warm-ups, cues
│   │   │       │   ├── holo.py          # exercises.glb reader: clip names, front-view clips, bounds
│   │   │       │   ├── progress.py      # Derived from rows: XP, levels, ranks, streaks, paths, today's plan, wedding boss
│   │   │       │   ├── legacy.py        # Import of the old browser-only "כבשתי!" flags
│   │   │       │   └── admin.py         # Grouping rows into sessions for the back office
│   │   │       ├── push_service.py      # קריאה לזירה: VAPID config, subscriptions, morning/evening texts
│   │   │       ├── cron_service.py      # APScheduler jobs (recurrences, pushes)
│   │   │       ├── backup_service.py    # ZIP / Excel backups
│   │   │       ├── cache_service.py     # In-memory statistics cache
│   │   │       ├── logging_service.py   # configure_logging(), print redirect
│   │   │       └── production_logging.py
│   │   ├── backups/                     # Generated backups (gitignored)
│   │   └── data/budget.db               # The SQLite database (gitignored)
│   ├── uploads/                         # User uploads at runtime (gitignored): vendor_files/, renovation journal photos
│   └── frontend/
│       ├── templates/
│       │   ├── layout/                  # base.html, _mobile_nav.html, _quick_add.html, _icons.html
│       │   ├── pages/                   # login, today, more, income, recurrences(_active), workout, workout_admin
│       │   ├── finances/                # base, index, transactions, transactions_import, statistics(_drilldown), backup
│       │   ├── wedding/                 # base + 16 feature pages incl. invite*.html (public RSVP)
│       │   ├── renovation/              # base (own shell) + index, rooms, tasks, ideas, supplies, journal, _compare
│       │   ├── partials/                # transactions/, income/, recurrences/, stats/ fragments
│       │   └── offline.html
│       └── static/
│           ├── css/                     # main.css, renovation.css, workout.css
│           ├── js/
│           │   ├── pages/               # One file per page: <module>-<page>.js (see convention 9)
│           │   ├── components/          # quick-add.js, form-manager.js, arena-push.js
│           │   ├── core/animations.js   charts/   vendor/
│           │   ├── workout.js  spanish.js
│           │   └── sw.js                # Service worker: static cache-first, HTML network-only
│           ├── holo/exercises.glb       # Exercise hologram (generated by tools/build_exercises_glb.py; README inside)
│           ├── spanish/deck.json        # The Spanish deck (static; progress is derived from spanish_reviews)
│           ├── icons/  manifest.json
├── tests/                               # pytest; *_e2e.py use TestClient, *_browser.py use Playwright
├── tools/
│   ├── refactor_baseline.py             # routes | schema picture for move-only refactors (diff against docs/refactor/*-baseline.txt)
│   ├── build_exercises_glb.py           # Builds static/holo/exercises.glb (stdlib only)
│   ├── generate_vapid_keys.py           # VAPID key pair for Web Push
│   └── gmail_max_import.gs              # Google Apps Script: mails the Max statement to the import endpoint
├── docs/
│   ├── specs/                           # One feature spec per feature (written by /feature-design before any code)
│   └── refactor/                        # Refactor specs + the route-table and schema baselines they are verified against
├── .claude/                             # Skills (feature, feature-design, ship, task skills) and the implementer agent
├── .github/workflows/ci.yml             # ruff + pytest (incl. Playwright) on every push to main and every PR
├── pyproject.toml                       # ruff + pytest config
├── requirements.txt  requirements-dev.txt  .pre-commit-config.yaml
├── Dockerfile  docker-compose.yml  .env.example
```

---

## Application Modules

### 1. היום (today) and the mobile shell (< 1024px)
Below `lg` the app uses a bottom tab bar (היום · חתונה · + · כספים · עוד) and a fixed per-module section header
(`layout/_mobile_nav.html`); desktop keeps the purple navbar and module sidebars and must look unchanged.
- `/` renders `pages/today.html` (built by `services/today.py`); on desktop it forwards to `/finances`. Module-only users are redirected to their module.
- The tab-bar "+" opens the quick-add sheet (`layout/_quick_add.html` + `static/js/components/quick-add.js`):
  an expense on כספים pages, a task elsewhere. `window.AppToast(msg, actionLabel, onAction)` shows the undo pill.
- A page's own primary action marked `data-quick-add="+ מוזמן"` is lifted into the section header's end slot.
- New mobile-only UI goes in `lg:hidden` containers; old blocks it replaces become `hidden lg:block`.

### 2. Finances
- Income and expense transactions by date, amount, category, user (payer), account; monthly view with category drilldowns; statistics (Chart.js donut + monthly bar); Excel export; ZIP database backups and restore.
- Recurring charges (`recurrences`) are materialised by `recurrence.py` (see **Recurring Transactions Engine**).
- **Card-statement import** (`services/card_statement.py`, `api/transactions.py` `/import/*`, page `/finances/transactions/import`): parses the monthly Max `transaction-details_export_*.xlsx`. Nothing is stored for the import itself: the payer is guessed from the holder's name above the header, charges already in the app are recognised by date + amount (recurrence rows by amount within a few days), and each merchant's category is learned from the newest transaction whose notes equal the merchant. `POST /api/transactions/import/auto` is `@public` but requires `Authorization: Bearer $IMPORT_TOKEN`; `tools/gmail_max_import.gs` posts the statement from Gmail once a day. `POST /import/undo` reverts a batch.

### 3. Wedding
A full sub-app: vendors (quotes with VAT, deposits, files, status, "tour mode" comparison), guests (RSVP, dietary, plus-ones, children, overnight stay, token invite links → public `/invite/{token}` pages), seating (drag-and-drop tables), lodging (rooms + assignments), tasks (owner = household member), budget, notes, ideas, timeline events, milestones, and **הזמנות מחו״ל** (`services/overseas.py`: samples ordered from abroad before the big order — lanes, time since ordering, big-order cost and the date it must leave, all derived).
`services/wedding_plan.py` owns the countdown, the date-anchored milestones, headcount and committed money; the `wedding_header` Jinja global feeds the section header.

### 4. Renovation (שיפוץ)
Rooms, tasks, ideas, supplies ("ציוד" — rows survive the task/room they belonged to), and a before/after journal whose two photo slots are uploaded separately (an entry usually starts with only a "before"). Deliberately **not** part of the finances/wedding layout: own `renovation/base.html`, own navigation, own `renovation.css`, so it stays simple for someone who only ever uses this section. Access: Yosef and Tsahala may open and edit it (`RENOVATION_USERS`, `RENOVATION_EDITORS` in `services/access.py`); Karina cannot see it. Every API write goes through `_require_editor` (403 otherwise). Photo uploads use `services/uploads.py`.

### 5. Workouts (הזירה)
Calisthenics tracker built as a game: `pages/workout.html` + `static/js/workout.js` + `static/css/workout.css`.
- Views on one page, switched by hash: `#home` (today's mission per quest path), `#map`, `#profile`, `#history`.
- A workout runs in a full-screen arena (warm-up → ready → set → rest → reward), one set at a time; after the
  warm-up the training waits on a "ready" screen until the athlete presses start. The session resumes
  from `localStorage` (`workout_active_session_v2`) after a refresh.
- XP, levels, ranks, streaks, achievements, today's plan and the "wedding boss" pace are derived from the saved rows in `services/workouts/progress.py` — never stored.
- Quest paths = `SKILL_PROGRESSIONS` (`services/workouts/catalog.py`); a station is conquered by 5 workouts in its rep range (counted, no button).
  Each station carries its `unit` (`reps`, or `sec` for a static hold — the UI labels the target accordingly),
  one `how` line and its own two form cues. A `prep=True` station (entry step, e.g. negative pull-ups) also
  counts as conquered once the station after it is, so adding one never sends anyone back. A saved row is matched back to its station **by name**
  (`STATION_INDEX` / `STATION_RENAMES`), so re-ordering a path never re-credits old history; the imported
  legacy flags stay numbered in `LEGACY_STATION_ORDER` and are translated on read (`services/workouts/legacy.py`).
  `POST /workouts/legacy-progress` imports the old browser-only "כבשתי!" flags once (kept in `system_settings`).
- **Exercise hologram**: `static/holo/exercises.glb`, one animation clip per exercise (`holo_key()` in `services/workouts/holo.py`),
  shown with `<model-viewer>` from jsDelivr. No file → the plain arena. The model is generated by
  `python3 tools/build_exercises_glb.py` (stdlib only; `--preview` for a stick sheet, `--render` for a shaded look). Each clip carries the prop its
  grip implies (bar / parallettes / pole); the glTF `extras.front_view_clips` names the clips the arena opens on the front camera. See `static/holo/README.md`.
- **Spanish between sets** (`services/spanish.py`, `api/spanish.py`, `static/js/spanish.js`, deck in `static/spanish/deck.json`): during rests the arena shows flash-cards. The only stored thing is one `spanish_reviews` row per graded card; stage (ladder 0, 1, 3, 7, 14, 30, 60, 120 days), due date, "words in your pocket", streaks and per-theme progress are replayed from those rows at read time.
- **קריאה לזירה (Web Push)**: `services/push_service.py` + `api/push.py` + `static/js/components/arena-push.js` (card on `#profile`). Morning push = today's mission (or the rest day `plan_today` recommends); evening push only on a day without a workout. A 404/410 from the push service deletes the subscription. Off unless the VAPID env vars are set.
- **Admin screen** `/workouts/admin` (`pages/workout_admin.html`, `static/js/pages/workouts-admin.js`): the back office for the saved rows.
  A **session** is the group of rows sharing `(user_id, date, workout_type, total_duration)` — the same grouping the history uses — so any of
  its row ids addresses it (`services/workouts/admin.py`, `api/workouts.py`). Everything derived follows from these rows, so an edit here moves the game state.
  Yonatan sees and edits only his own sessions (`people.workout_people`); the household manages everyone who trains.

---

## Database Schema

All tables in one SQLite file, `app/backend/data/budget.db` (override with `BUDGET_DB_PATH`). Connections use
`row_factory = sqlite3.Row` and `PRAGMA foreign_keys = ON`. The before-picture of a fresh database (every CREATE
statement and every seeded row) is `docs/refactor/schema-baseline.txt`; regenerate it with
`python tools/refactor_baseline.py schema` when the schema changes on purpose.

**Finance (`db/finance.py`):**
- `categories` — `id, name (UNIQUE), is_saving (bool)`. Seeded: משכורת, קליניקה, בריאות, חסכונות (is_saving=1), פנאי, הוצאות בית, רכב, תחבורה, אוכל בחוץ.
- `users` — `id, name (UNIQUE)`. Seeded `Yosef`, `Karina` (migrated from Hebrew names) and `Yonatan` (workouts only; `people.household()` stays Yosef/Karina so he never appears as a payer or task owner).
- `accounts` — `id, name (UNIQUE)`. Seeded מזומן and כרטיס אשראי.
- `transactions` — `id, date, amount, category_id (FK), user_id (FK), account_id (FK nullable), notes, tags, recurrence_id (FK nullable), period_key`. UNIQUE `(recurrence_id, period_key)`.
- `recurrences` — `id, name, amount, category_id, user_id, frequency (monthly/weekly/yearly), day_of_month, weekday, next_charge_date, active, account_id`.
- `recurrence_skips` — `(recurrence_id, period_key)` PK.
- `system_settings` — `key (PK), value, updated_at`. Flags and markers (`wedding_milestones_seeded`, `push_sent:<kind>:<date>`, legacy workout flags, …).

**Wedding (`db/wedding.py`):**
- `wedding_vendors` (+ `portions_ordered` = meals booked with the caterer), `vendor_quote_items`, `vendor_files` (`original_name, stored_name, file_size, mime_type`; bytes under `app/uploads/vendor_files/`).
- `wedding_guests` (RSVP, meal preference, `children_count`, `staying_overnight`, invite token), `wedding_tasks` (`owner` = nullable `users.name`), `wedding_budget_items`, `wedding_settings` (`key/value`; `venue_capacity` = seats at the venue).
- `wedding_notes`, `wedding_ideas`, `wedding_timeline_events`.
- `wedding_seating_tables`, `wedding_seating_assignments` (one guest may hold several seats; rebuilt once to drop an old UNIQUE(guest_id)).
- `wedding_rooms` (14 seeded: 3 caravans, 3 tents, 8 double rooms), `wedding_room_assignments` (UNIQUE guest).
- `wedding_milestones` — `id, title, offset_days, kind, completed, custom_date, sort_order`. Dates are `wedding_date + offset_days` unless `custom_date` pins one; 12 defaults seeded once a wedding date exists.
- `wedding_overseas_items` — `title, url, store, sample_price, quantity_needed, stage (to_order/ordered/arrived/approved/rejected), ordered_at, arrived_at, created_by`; `wedding_overseas_comments` (cascade).

**Renovation (`db/renovation.py`):** `renovation_rooms` (7 seeded), `renovation_tasks` (`status, priority, due_date`), `renovation_ideas` (`status, color, image_url, link_url`), `renovation_supplies` (`quantity, status, room_id, task_id` — both SET NULL), `renovation_journal` (`entry_date, notes, before_photo, after_photo` = stored UUID filenames). All carry `created_by` (the login name).

**Arena (`db/workouts.py`):**
- `workouts` — `id, user_id (FK), date, workout_type, total_duration, exercise_name, total_sets, total_reps, skill_key, stage_index, max_reps`. One row per exercise per session.
- `spanish_reviews` — `user_id, item_id (id in deck.json), reviewed_at, grade (0–3), mode (intro/recall), context`.
- `push_subscriptions` — `user_id (FK cascade), endpoint (UNIQUE), p256dh, auth, created_at`. One per device; subscribing an existing endpoint re-points it to the current user.

**Migrations** are inline and idempotent in each module's `ensure_schema(conn)`, called in order (finance → wedding → renovation → workouts) by `initialise_database()`. New columns: `PRAGMA table_info()` check + `ALTER TABLE ADD COLUMN` (never NOT NULL without a DEFAULT); new tables: `CREATE TABLE IF NOT EXISTS` after the tables they reference. No migration framework. The `db-migration` skill has the exact pattern.

---

## Authentication and Access

**No user table with hashed passwords.** Credentials come from environment variables, `USER_PASSWORD_<USERNAME>` for each name in `ALL_USERNAMES` (`services/access.py`). Username match is case-insensitive.

**Per-user module access** (`services/access.py`, enforced by `AuthMiddleware.can_access_path`; a blocked page GET is redirected to `home_path_for(user)`, a blocked API call gets 403):
- `YOSEF` — everything. `KARINA` — everything except renovation.
- `TSAHALA` — renovation only; `YONATAN` — workouts only (`MODULE_ONLY_USERS`: allowed prefixes + landing page). `layout/base.html` hides the tab bar and other modules' links for them.
- Renovation writes additionally need `can_edit_renovation` (Yosef, Tsahala).

**Session flow:** `POST /login` checks the env vars → `request.session["user"] = {"username": KEY}` → a signed fallback cookie `auth_user` (`itsdangerous.URLSafeSerializer(SESSION_SECRET_KEY, salt="auth-user")`). `AuthMiddleware` (Starlette `BaseHTTPMiddleware`) reads the session, falls back to the cookie, else 302 to `/login`. 24-hour max_age; production `SameSite=None; Secure`, development `lax`/insecure.

**Public routes** carry `@public` (`auth.py`); `build_public_route_matchers()` scans the registered routes at startup. Today: `/login` (GET, POST), `/invite/{token}` (GET), `/invite/{token}/rsvp` (POST), `/api/transactions/import/auto` (POST, token-guarded). Include routers directly in `main.py` (nesting is only safe where no route is `@public`, as in `api/wedding/__init__.py`).

**Rate limiting:** IP-based in-memory counter for `/login` in `routes/auth.py` (`_login_attempts`). No external store.

---

## Recurring Transactions Engine

Lives in `recurrence.py`. A **catch-up / materialisation** model — not real-time.

- `apply_recurring(today=None)` iterates all active recurrences where `next_charge_date IS NOT NULL`
- For each: loops `while next_charge_date <= today`, inserting a transaction per due period
- Each insert is idempotent via `UNIQUE(recurrence_id, period_key)`; `recurrence_skips` is checked first
- Advances `next_charge_date` by one interval after each insert; amounts stored as `-abs(amount)`
- monthly = +1 month preserving day (clamped to last day); weekly = +7 days; yearly = +1 year

**Triggered by:** app startup (via `CronService`), the daily cron at 03:15 Asia/Jerusalem, `POST /api/system/apply-recurring`, and after `POST /api/recurrences`.

---

## Routers (as included in `main.py`)

| Router | Prefix | Description |
|---|---|---|
| `routes.auth` | — | `/login`, `/logout` |
| `routes.home` | — | `/` (היום), `/more`, `/sw.js` |
| `routes.finances` | — | `/finances/*` pages; `/income`, `/recurrences`, `/recurrences/{id}/…` form posts and inline rows |
| `routes.wedding` | — | `/wedding/*` pages; public `/invite/{token}` |
| `routes.partials` | — (no prefix) | Inline-edit fragments `/transactions/{id}/row|edit-inline|delete-inline`, same for `/income`, `/recurrences` (the recurrence ones are shadowed by `routes.finances`, which registers first) |
| `routes.debug_logs` | — | `/debug/logs`, `/debug/logs/auth`, `/debug/logs/errors` |
| `routes.workouts` | — | `/workouts`, `/workouts/admin`, `POST /workouts`, `POST /workouts/legacy-progress` |
| `routes.renovation` | `/renovation` | Dashboard, rooms, tasks, ideas, supplies, journal |
| `api.transactions` | `/api/transactions` | CRUD, duplicate, `/export`, `/import/preview|import|auto|undo` |
| `api.recurrences` | `/api/recurrences`, `/api/system` | CRUD + apply-once; `POST /api/system/apply-recurring` |
| `api.statistics` | `/api/statistics` | Aggregates + cache clear |
| `api.backup` | `/api/backup` | ZIP + Excel backups, restore |
| `api.wedding` | `/api/wedding` | 13 feature routers aggregated in the package `__init__` |
| `api.renovation` | `/api/renovation` | Rooms, tasks, ideas, supplies, journal, journal photos |
| `api.workouts` | `/api/workouts` | Back office: sessions + imported stations |
| `api.push` | `/api/workouts/push` | `GET /key`, `POST`/`DELETE /subscribe`, `POST /test` |
| `api.spanish` | `/api/workouts/spanish` | `GET /queue`, `GET /stats`, `POST /reviews` |
| `api.today` | `/api` | `GET /today`, `GET /quick-add/options` |

The full, sorted route table (197 routes) with the public matchers is `docs/refactor/route-table-baseline.txt`;
`python tools/refactor_baseline.py routes` regenerates it. Update the file when routes change on purpose.

---

## Services worth knowing

- **`CronService`** — APScheduler `BackgroundScheduler`: `apply_recurring()` at startup and daily 03:15; when the VAPID keys are set, the arena pushes at 08:40 and 21:00 (Asia/Jerusalem). Single uvicorn worker, so there is exactly one scheduler.
- **`push_service`** — see Workouts. Keys from `tools/generate_vapid_keys.py`.
- **`backup_service`** — ZIP archives of the SQLite file (restore copies it back), monthly Excel export via openpyxl.
- **`cache_service`** — in-memory cache for statistics responses; **invalidate it on any write that affects statistics**.
- **`uploads`** — shared rules for user uploads (extension allow-list, size cap, magic-byte sniffing, random stored names). Both upload paths (vendor files, journal photos) must go through it.
- **`logging_service` / `production_logging`** — rotating `logs/server.log`; print statements are redirected in production; `/debug/logs*` serve the tail.

---

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `SESSION_SECRET_KEY` | **Yes** | Signs session and auth cookies. Missing = startup crash (by design; pytest gets a throwaway). |
| `USER_PASSWORD_YOSEF`, `USER_PASSWORD_KARINA` | **Yes** | Login passwords |
| `USER_PASSWORD_TSAHALA`, `USER_PASSWORD_YONATAN` | For those logins | Renovation-only / workouts-only users |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | For push | Base64url P-256 keys (`python tools/generate_vapid_keys.py`). Missing = arena push off. |
| `VAPID_SUBJECT` | No | `mailto:` contact sent to the push services |
| `IMPORT_TOKEN` | No | Bearer token for `POST /api/transactions/import/auto`. Unset = endpoint off. |
| `BUDGET_DB_PATH` | No | Database file location (tests and `tools/refactor_baseline.py` set it) |
| `FORCE_DB_RESET=1` | No | Drop and recreate all tables at startup |
| `AUTH_ENABLED=0` | No | Disable auth — pytest only (requires `PYTEST_CURRENT_TEST`) |
| `RAILWAY_ENVIRONMENT` / `ENVIRONMENT=production` | No | Production mode (cookie flags, logging) |
| `ALLOWED_HOSTS` | No | Comma-separated trusted hosts |
| `COOKIE_SAMESITE`, `COOKIE_SECURE`, `SESSION_COOKIE_DOMAIN` | No | Cookie overrides (dev only) |

---

## Deployment

- **Docker:** `python:3.12-slim`, single worker (`--workers 1`) so APScheduler runs once; `TZ=Asia/Jerusalem`.
- **Platform:** Railway (auto-detected via `RAILWAY_ENVIRONMENT`). The DB file and `app/uploads/` live on the container's disk.
- **docker-compose:** the SQLite file is bind-mounted as `./budget.db`.

---

## Key Patterns and Conventions

1. **No ORM** — raw `sqlite3` with `Row`; services take a connection, routes get one from `Depends(get_db_conn)`.
2. **No JS build step** — vanilla JS served as static files; vendor libs are checked in.
3. **Inline, idempotent migrations** in the module's `ensure_schema(conn)` under `db/` (see Database Schema).
4. **Derive, don't store** — totals, streaks, levels, conquered stations, Spanish stages, overseas deadlines are computed from rows at read time; never add a column for something the rows already imply.
5. **Idempotent recurrences** — `UNIQUE(recurrence_id, period_key)` is the safety net.
6. **`@public` decorator** marks auth-bypassing routes; routers are included directly in `main.py`.
7. **Hebrew UI, English code** — identifiers, routes, column names in English; every user-visible string in Hebrew.
8. **Amounts** — income positive, expenses `-abs(amount)`.
9. **Page scripts** live in `static/js/pages/<module>-<page>.js`, included with a plain `<script src="…?v=YYYYMMDD">` at the spot in the template where the script belongs (usually the end of the page's content); server data reaches them through one `<script type="application/json" id="<page>-data">` block read into `PAGE_DATA`. Bump `?v=` whenever the file changes — `sw.js` serves `/static/` cache-first by URL. No inline `<script>` in page templates.
10. **Layering** — `routes/` and `api/` import from `services/`, `db/`, `schemas/`, `templating.py`; `services/` never import from `routes/` or `api/`. Path constants that depend on a file's location (`Path(__file__)…`) are re-derived when a file moves — the one thing a "move verbatim" refactor must not copy blindly.
11. **Desktop pixel-identical** unless a change is explicitly for desktop; new mobile UI in `lg:hidden` containers.
12. **Templates** render with `templates.TemplateResponse(request, "x.html", {...})` (request first — Starlette 1.x).
13. **Tests** use the `app_client` fixture (fresh temp DB via `initialise_database()`, `AUTH_ENABLED=0`); browser suites (`test_*_browser.py`) start uvicorn on a free port and drive Playwright, and skip themselves when Playwright is missing.
14. **Move-only refactors** are specified in `docs/refactor/`, built by the implementer, and proven with `tools/refactor_baseline.py` (route table + schema unchanged), the suite, and a line-by-line comparison of moved code.

---

## Running Locally

```bash
pip install -r requirements-dev.txt      # runtime deps + ruff, pytest, pre-commit, playwright
python -m playwright install chromium    # once, for the browser suites
pre-commit install                       # once per clone

export SESSION_SECRET_KEY="your-secret-key"
export USER_PASSWORD_YOSEF="..."
export USER_PASSWORD_KARINA="..."
uvicorn app.backend.app.main:app --reload --port 8000     # or: docker-compose up
```

### Lint, tests, CI

- `ruff check .` must pass. Config in `pyproject.toml` (rules E, F, I, B, UP; line length 120 with E501 off; the deliberate exceptions are listed there with their reason). `ruff format` is **not** applied.
- `python -m pytest` (config in `pyproject.toml`): 346 tests as of 2026-10-19, all green on `main`. The suite never touches `app/backend/data/budget.db`.
- `.github/workflows/ci.yml` runs lint + the full suite (Chromium installed) on every push to `main` and every PR, on Python 3.12 like the Dockerfile.
- The pinned local interpreter is `.venv/Scripts/python.exe`; the global Python carries the wrong Starlette.

---

## AI workflow (Claude Code)

The session model is Fable; it does the thinking. Opus does the typing. Skills and agents live in `.claude/`.

| Ask | Use | What happens |
|---|---|---|
| A new feature or screen | `/feature <idea>` | Fable designs it with `feature-design`, writes `docs/specs/<date>-<slug>.md`, pauses for approval (`--go` skips), spawns the **`implementer`** agent (Opus) to build and test it, reviews the diff in-session, then ships. |
| Just the design | `/feature-design <idea>` | Three framings (straight / house style / subtraction), the generic detector, a Hebrew name, one signature detail, a spec file. No code. |
| A settled spec, a precise fix, or a move-only refactor | `Agent(subagent_type: "implementer")` | Opus implements from the spec (`docs/specs/` or `docs/refactor/`), runs the pinned suite, never commits. |
| Commit / push / PR | `/ship [-m "..."] [--main] [--no-pr]` | Preflight for stray `*.db`/backups/secrets, ruff + tests, `claude/<slug>` branch, conventional commit with attribution, push, PR via `gh`. |

Rules the skills enforce and every change should respect: Hebrew UI / English code; desktop pixel-identical unless the feature is desktop; derive, never store what rows already imply; inline idempotent migrations; no new runtime dependencies or build steps; the implementer never touches git.

Task skills (`add-transaction-category`, `add-recurrence-frequency`, `api-endpoint`, `db-migration`, `wedding-vendor-workflow`) encode the exact code patterns; the implementer reads the ones that apply.
