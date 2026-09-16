# Project Overview — Expense Tracker & Wedding Planner

## What This App Is

A personal finance + wedding planning web application built for two specific users: **Yosef** and **Karina**. The UI is in Hebrew; the code, identifiers, and API surface are in English.

It is deployed on **Railway** as a Docker container and is a server-rendered monolith. There is no client-side framework and no JS build step.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Web framework | FastAPI 0.110.0 + Uvicorn 0.29.0 |
| Middleware/sessions | Starlette 0.36.3 |
| Database | SQLite (raw `sqlite3`, no ORM) |
| Schema validation | Pydantic v2 |
| Templating | Jinja2 3.1.4 (server-side rendered) |
| Background jobs | APScheduler 3.10.4 |
| Excel export | OpenPyXL 3.1.5 |
| Auth cookies | itsdangerous (signed cookies) |
| Frontend JS | Vanilla JS, no bundler, no framework |
| Charts | Chart.js (vendor-bundled) |
| CSS | Single `main.css` |
| PWA | Service worker at `/sw.js` |

---

## Project Structure

```
expense_tracker/
├── app/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── main.py              # App factory, middleware, routers, lifecycle
│   │   │   ├── db.py                # Schema, migrations, DB connection helpers
│   │   │   ├── auth.py              # @public decorator, route matcher builder
│   │   │   ├── recurrence.py        # Recurring transaction materialization engine
│   │   │   ├── seed_data.py         # Legacy seed helpers
│   │   │   ├── api/                 # JSON REST endpoints
│   │   │   │   ├── transactions.py  # CRUD + export
│   │   │   │   ├── recurrences.py   # CRUD + apply-once
│   │   │   │   ├── statistics.py    # Aggregated stats
│   │   │   │   ├── backup.py        # ZIP + Excel backup
│   │   │   │   ├── wedding.py       # Full wedding module API (incl. milestones)
│   │   │   │   └── today.py         # /api/today aggregate + /api/quick-add/options
│   │   │   ├── routes/              # HTML page routes (Jinja2 rendering)
│   │   │   │   ├── pages.py         # All page views, login/logout, dashboard
│   │   │   │   ├── partials.py      # HTMX-style partial HTML fragments
│   │   │   │   ├── workouts.py      # Workouts page
│   │   │   │   └── debug_logs.py    # Debug log viewer
│   │   │   ├── schemas/             # Pydantic models
│   │   │   │   ├── transactions.py
│   │   │   │   ├── recurrences.py
│   │   │   │   ├── backup.py
│   │   │   │   └── workouts.py
│   │   │   └── services/
│   │   │       ├── auth_middleware.py     # AuthMiddleware class
│   │   │       ├── backup_service.py     # ZIP/Excel backup implementation
│   │   │       ├── cache_service.py      # In-memory stats cache
│   │   │       ├── hebrew_dates.py       # Hebrew relative-date labels (באיחור ביומיים, בעוד 4 ימים)
│   │   │       ├── people.py             # Household users (Yosef/Karina) with display names + colors
│   │   │       ├── today.py              # היום queue: urgent tasks across modules + month totals
│   │   │       ├── wedding_plan.py       # Countdown, date-anchored milestones, headcount, committed money
│   │   │       ├── cron_service.py       # APScheduler background jobs
│   │   │       ├── logging_service.py    # configure_logging(), print redirect
│   │   │       └── production_logging.py # Railway-specific logging
│   │   ├── backups/                 # ZIP and Excel backup files
│   │   └── data/budget.db           # SQLite database
│   └── frontend/
│       ├── templates/
│       │   ├── finances/            # base.html, index, transactions, statistics, backup
│       │   ├── wedding/             # 15 wedding feature templates
│       │   ├── pages/               # login.html
│       │   ├── layout/              # Shared layout fragments
│       │   └── partials/            # Reusable partial HTML
│       └── static/
│           ├── css/main.css
│           └── js/
│               ├── charts/          # donut.js, monthly.js, helpers.js
│               ├── components/      # form-manager.js
│               ├── core/            # animations.js
│               ├── vendor/          # Chart.js and other third-party libs
│               ├── sw.js            # Service worker (PWA)
│               └── workout.js
├── tests/
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env
```

---

## Application Modules

### 1. Finance Module
- Track income and expense transactions by date, amount, category, user, and account
- Monthly budget view with category drilldowns
- Statistics with charts (Chart.js: donut and monthly bar)
- Recurring (subscription) expense management
- Excel export and ZIP database backups

### 2. Wedding Module
A full second sub-app inside the same codebase:
- Vendor management (quotes, deposits, files, contact info, status)
- Guest management with RSVP, dietary preferences, plus-ones, children, overnight stay
- Seating plan (drag-and-drop table layout)
- Lodging and room assignments for overnight guests
- Wedding task list
- Wedding budget tracker
- Notes, ideas, timeline events
- RSVP invite links (token-based, public routes)

### 3. Workouts Module
Calisthenics tracker built as a game ("הזירה"): `pages/workout.html` + `static/js/workout.js` + `static/css/workout.css`.
- Views on one page, switched by hash: `#home` (today's mission per quest path), `#map`, `#profile`, `#history`.
- A workout runs in a full-screen arena (set → rest → reward), one set at a time; the session resumes
  from `localStorage` (`workout_active_session_v2`) after a refresh.
- XP, levels, ranks, streaks and achievements are derived from history in `routes/workouts.py` — never stored.
- Quest paths = `SKILL_PROGRESSIONS`; a station is conquered by 5 workouts in its rep range (counted, no button).
  `POST /workouts/legacy-progress` imports the old browser-only "כבשתי!" flags once (kept in `system_settings`).
- Optional exercise hologram: `static/holo/exercises.glb`, one animation clip per exercise (`holo_key()`),
  shown with `<model-viewer>` from jsDelivr. No file → the plain arena. See `static/holo/README.md`.

---

## Database Schema

All tables in a single SQLite file at `app/backend/data/budget.db`. Connection uses `row_factory = sqlite3.Row` and `PRAGMA foreign_keys = ON`.

**Finance tables:**
- `categories` — `id, name (UNIQUE), is_saving (bool)`. Seeded with Hebrew names: משכורת, קליניקה, בריאות, חסכונות (is_saving=1), פנאי, הוצאות בית, רכב, תחבורה, אוכל בחוץ.
- `users` — `id, name (UNIQUE)`. Seeded with `Yosef` and `Karina` (migrated from Hebrew names).
- `accounts` — `id, name (UNIQUE)`. Seeded with מזומן (cash) and כרטיס אשראי (credit card).
- `transactions` — `id, date, amount, category_id (FK), user_id (FK), account_id (FK nullable), notes, tags, recurrence_id (FK nullable), period_key`. UNIQUE on `(recurrence_id, period_key)` for idempotency.
- `recurrences` — `id, name, amount, category_id (FK), user_id (FK), frequency (monthly/weekly/yearly), day_of_month, weekday, next_charge_date, active (bool), account_id (nullable FK)`.
- `recurrence_skips` — `(recurrence_id, period_key)` PK. Tracks skipped occurrences.
- `system_settings` — `key (PK), value, updated_at`. Key/value metadata store.

**Wedding tables:**
- `wedding_vendors`, `vendor_quote_items`, `vendor_files`
- `wedding_guests`, `wedding_tasks`, `wedding_budget_items`, `wedding_settings`
- `wedding_notes`, `wedding_ideas`, `wedding_timeline_events`
- `wedding_seating_tables`, `wedding_seating_assignments`
- `wedding_rooms`, `wedding_room_assignments`
- `wedding_milestones` — `id, title, offset_days, kind, completed, custom_date, sort_order`. Dates are always computed as `wedding_date + offset_days` (so changing the wedding date moves them) unless `custom_date` pins one. 12 defaults are seeded once, the first time a wedding date exists (flag `wedding_milestones_seeded` in `system_settings`).
- `wedding_tasks.owner` — nullable `users.name` of the household member who took the task (same list as the finances payer).
- `wedding_vendors.portions_ordered` — meals booked with the catering vendor; `wedding_settings.venue_capacity` — seats at the venue.

**Workouts table:**
- `workouts` — `id, user_id (FK), date, workout_type, total_duration, exercise_name, total_sets, total_reps, skill_key, stage_index, max_reps`. One row per exercise per session. `skill_key`/`stage_index` = the quest station trained (older rows are matched by their `"hebrew (English)"` name); `max_reps` = best single set, for personal records.

**Migrations** are inline in `initialise_database()` in `db.py`, using `PRAGMA table_info()` to detect and add missing columns. No migration framework is used.

---

## Authentication

**No user table with hashed passwords.** Credentials come entirely from environment variables: `USER_PASSWORD_YOSEF` and `USER_PASSWORD_KARINA`. Username match is case-insensitive.

**Session-based auth:**
1. On login (`POST /login`), credentials are checked against env vars
2. On success: `request.session["user"] = {"username": user_key}` is set
3. A signed fallback cookie `auth_user` is also set using `itsdangerous.URLSafeSerializer(SESSION_SECRET_KEY, salt="auth-user")`
4. `AuthMiddleware` (Starlette `BaseHTTPMiddleware`) checks session first, falls back to cookie
5. Unauthenticated requests → 302 redirect to `/login`

**Public routes** are decorated with `@public` (from `auth.py`). `build_public_route_matchers()` scans all registered routes at startup and passes regex+methods tuples to `AuthMiddleware`.

**Rate limiting:** IP-based in-memory counter in `pages.py`. No external store.

**Session config:**
- `SESSION_SECRET_KEY` is required — missing key = startup crash (by design)
- 24-hour max_age
- Production (Railway): `SameSite=None; Secure=True`
- Development: `SameSite=lax; Secure=False`

---

## Recurring Transactions Engine

Lives in `recurrence.py`. Uses a **catch-up / materialization** model — not real-time.

- `apply_recurring(today=None)` iterates all active recurrences where `next_charge_date IS NOT NULL`
- For each: loops `while next_charge_date <= today`, inserting a transaction per due period
- Each insert is idempotent via `UNIQUE(recurrence_id, period_key)` constraint
- Checks `recurrence_skips` before inserting
- Advances `next_charge_date` by one interval after each insert
- Amounts are stored as negative (`-abs(amount)`) to mark them as expenses
- Frequency advances: monthly = +1 month preserving day (clamped to last day); weekly = +7 days; yearly = +1 year

**Triggered by:**
1. App startup (immediately via `CronService`)
2. Daily cron at 03:15 server time (Asia/Jerusalem)
3. `POST /api/system/apply-recurring`
4. After creating a new recurrence via `POST /api/recurrences`

---

## API Routes

| Router | Prefix | Description |
|---|---|---|
| `pages_router` | (no prefix) | HTML page views (Jinja2) |
| `partials_router` | `/partials` | Partial HTML fragments |
| `transactions_api` | `/api/transactions` | CRUD + Excel export |
| `recurrences_api` | `/api/recurrences` | CRUD + apply-once |
| `system_api` | `/api/system` | `POST /apply-recurring` |
| `statistics_api` | `/api/statistics` | Aggregated stats + cache clear |
| `backup_api` | `/api/backup` | ZIP + Excel backups |
| `wedding_api` | `/api/wedding` | Full wedding module CRUD |
| `workouts_router` | (no prefix) | Workouts page + data |
| `debug_logs_router` | (no prefix) | Debug log viewer |
| `today_api` | `/api` | `GET /today` (היום aggregate), `GET /quick-add/options` |

---

## Mobile shell (< 1024px)

Below `lg` the app uses a bottom tab bar (היום · חתונה · + · כספים · עוד) and a fixed per-module section header
(`layout/_mobile_nav.html`); desktop keeps the purple navbar and module sidebars and must look unchanged.
- `/` renders `pages/today.html` (היום); on desktop it forwards to `/finances`. Renovation-only users are redirected.
- The tab-bar "+" opens the quick-add sheet (`layout/_quick_add.html` + `static/js/components/quick-add.js`):
  an expense on כספים pages, a task elsewhere. `window.AppToast(msg, actionLabel, onAction)` shows the undo pill.
- A page's own primary action marked `data-quick-add="+ מוזמן"` is lifted into the section header's end slot.
- New mobile-only UI goes in `lg:hidden` containers; old blocks it replaces become `hidden lg:block`.

## Services

- **`AuthMiddleware`** — per-request auth guard. Reads session, falls back to signed cookie. Lives in `services/auth_middleware.py`.
- **`CronService`** — APScheduler `BackgroundScheduler`. Two jobs: immediate startup run + daily 03:15. Calls `apply_recurring()`.
- **`backup_service`** — creates ZIP archives of the SQLite DB; restore copies file back; monthly Excel export via openpyxl.
- **`cache_service`** — simple in-memory cache for statistics API responses.
- **`logging_service` / `production_logging`** — rotating file log at `logs/server.log`. Redirects print statements in production.

---

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `SESSION_SECRET_KEY` | **Yes** | Signs session and auth cookies. Missing = startup crash. |
| `USER_PASSWORD_YOSEF` | **Yes** | Login password for Yosef |
| `USER_PASSWORD_KARINA` | **Yes** | Login password for Karina |
| `BUDGET_DB_PATH` | No | Override DB file location (used in tests) |
| `FORCE_DB_RESET=1` | No | Drop and recreate all tables at startup |
| `AUTH_ENABLED=0` | No | Disable auth (pytest only — requires `PYTEST_CURRENT_TEST`) |
| `RAILWAY_ENVIRONMENT` | No | Set by Railway; switches production mode |
| `ENVIRONMENT=production` | No | Alternative production flag |
| `ALLOWED_HOSTS` | No | Comma-separated trusted hosts override |
| `COOKIE_SAMESITE` | No | Override SameSite cookie attribute (dev only) |
| `COOKIE_SECURE` | No | Override Secure cookie attribute (dev only) |
| `SESSION_COOKIE_DOMAIN` | No | Override cookie domain (dev only) |

---

## Deployment

- **Docker:** Single worker enforced (`--workers 1`) to prevent multiple APScheduler instances
- **Platform:** Railway (auto-detected via `RAILWAY_ENVIRONMENT`)
- **Timezone:** `Asia/Jerusalem` (set in Dockerfile)
- **SQLite file:** Bind-mounted from host as `./budget.db` in docker-compose

---

## Key Patterns and Conventions

1. **No ORM** — all DB access is raw `sqlite3` with named-column `Row` factory
2. **No JS build step** — vanilla JS files are served directly as static files
3. **Inline migrations** — schema changes are added as `ALTER TABLE ADD COLUMN` checks in `initialise_database()`
4. **Idempotent recurrences** — `UNIQUE(recurrence_id, period_key)` constraint is the safety net
5. **`@public` decorator** — marks routes that bypass auth; scanned at startup to build matchers
6. **Hebrew UI, English code** — all identifiers, API routes, and variable names are English; all user-visible strings are Hebrew
7. **Amounts convention** — income is positive, expenses are negative (stored as `-abs(amount)`)
8. **Tests** use `BUDGET_DB_PATH` env var to point at a temp DB and `AUTH_ENABLED=0` to bypass auth

---

## Running Locally

```bash
# From project root
pip install -r requirements.txt

# Required env vars
export SESSION_SECRET_KEY="your-secret-key"
export USER_PASSWORD_YOSEF="..."
export USER_PASSWORD_KARINA="..."

# Run
uvicorn app.backend.app.main:app --reload --port 8000
```

Or with Docker:
```bash
docker-compose up
```
