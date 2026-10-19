# Refactor spec — split the two giant route modules (phase 2 of the repo cleanup)

**Kind:** pure refactor. No behaviour change, no UI change, no schema change, no new dependency.
**Branch:** `claude/split-route-modules` (stacked on `claude/repo-hygiene`, PR #45). You do not touch git.
**Definition of done:** the Acceptance criteria section, all of it.

## Why

`routes/pages.py` (2,629 lines) holds 37 handlers for login, the home shell, finances and wedding in one file.
`routes/workouts.py` (2,015 lines) holds 4 routes and ~1,900 lines of game data and derivation logic that
`api/workouts.py`, `api/push.py`, `api/spanish.py`, `services/push_service.py` and seven test files import from a
*routes* module. Four route modules each build their own `Jinja2Templates`, so the one Jinja global
(`wedding_header`) exists in only one of them. Splitting by module is what makes the later phases
(wedding API package, migrations per module, pulling inline JS out of templates) tractable.

## Rules for this refactor

1. **Move, don't edit.** Function and constant bodies move verbatim. Do not rename functions, do not change
   signatures, do not "improve" anything on the way, do not reorder statements inside a function. The reviewer
   will read the diff with `git diff --color-moved=dimmed-zebra`; anything that is not a pure move must be
   explainable in one line in your report.
2. **Imports follow the code.** Each new module imports only what its code uses. `ruff check .` must pass
   (it catches undefined names and unused imports). Do not use `import *`. Do not add re-export shims
   "for compatibility" — update the importers instead (they are all listed below).
3. **One Jinja environment.** New module `app/backend/app/templating.py` owns `ROOT_DIR`, `FRONTEND_DIR`,
   `TEMPLATES_DIR`, `STATIC_DIR` (same values as today: `ROOT_DIR = Path(__file__).resolve().parents[2]`,
   i.e. `.../expense_tracker/app`) and the single `templates = Jinja2Templates(directory=str(TEMPLATES_DIR))`.
   It also owns `_wedding_header()` (moved from `pages.py`) and registers
   `templates.env.globals["wedding_header"] = _wedding_header` at import. Every route module
   (`pages.py` successors, `partials.py`, `renovation.py`, `workouts.py`) does
   `from ..templating import templates` and deletes its own `ROOT_DIR/FRONTEND_DIR/TEMPLATES_DIR` and
   `Jinja2Templates(...)` lines. `main.py` keeps its own `ROOT_DIR/FRONTEND_DIR/STATIC_DIR` (it mounts static
   files and the log dir before anything else imports) — do not touch that.
4. **Routers are included directly in `main.py`, never nested** with `router.include_router(...)`.
   The requirements.txt comment explains why: nested routers hide `@public` routes from
   `build_public_route_matchers`. Keep `@public` on exactly the handlers that have it today
   (`login_page`, `login_post`, `invite_rsvp_page`, `invite_rsvp_submit`; `service_worker` and the
   transactions import endpoint — check with grep, do not guess).
5. **Registration order of the finances routes before `partials_router` must be preserved.**
   `/recurrences/{rec_id}/row`, `/recurrences/{rec_id}/edit-inline` (GET and POST) and
   `/recurrences/{rec_id}/delete-inline` are registered twice today — once in `pages.py`, once in
   `partials.py` — and the `pages.py` copies win because `pages_router` is included first. Keep it that way:
   in `main.py` include the new routers in this order: auth, home, finances, wedding, then `partials_router`
   and the rest exactly as today. Do **not** delete the duplicates in `partials.py` in this refactor (a
   later, separate change).
6. Hebrew UI / English code, as always. No template, CSS or JS file changes at all in this refactor.

## Target layout

### `routes/pages.py` → four modules, then delete `pages.py`

| New file | Routes (handler names as today) | Module-level helpers / state that move with them |
|---|---|---|
| `routes/auth.py` | `GET /login` `login_page`, `POST /login` `login_post`, `GET /logout` `logout` | `_LOGIN_WINDOW_SECONDS`, `_LOGIN_MAX_ATTEMPTS`, `_login_attempts`, its `Lock`, `_check_login_rate_limit`, `_get_session_secret`, the rate-limit comment block |
| `routes/home.py` | `GET /` `index`, `GET /more` `more_page`, `GET /sw.js` `service_worker` | nothing else |
| `routes/finances.py` | `GET /finances` `finances_dashboard`, `/finances/transactions`, `/finances/transactions/import`, `/finances/income`, `POST /income` `create_income_form`, `/finances/recurrences`, `/finances/recurrences/active`, `POST /recurrences` `create_recurrence_form`, `POST /recurrences/{rec_id}/toggle-active`, `GET /recurrences/{rec_id}/row`, `GET+POST /recurrences/{rec_id}/edit-inline`, `POST /recurrences/{rec_id}/delete-inline`, `/finances/statistics`, `/finances/statistics/drilldown`, `/finances/backup` | `_first_weekday_in_month`, `_get_main_user_ids` (both used only by finances handlers — verify with grep before moving) |
| `routes/wedding.py` | `GET /wedding` `wedding_dashboard`, `/wedding/lodging`, `/wedding/vendors`, `/wedding/vendors/{vendor_id}`, `/wedding/guests`, `/wedding/tasks`, `/wedding/budget`, `/wedding/notes`, `/wedding/ideas`, `/wedding/overseas`, `/wedding/seating`, `/wedding/timeline`, `/wedding/milestones`, `GET /invite/{token}` `invite_rsvp_page`, `POST /invite/{token}/rsvp` `invite_rsvp_submit` | `_wedding_total_budget`, `_wedding_hero`, `_guest_count_engine`, `_TASK_GROUPS`, `_TASK_CATEGORY_LABELS` |

Each new module: `router = APIRouter(tags=["pages"])` (same tag as today so the OpenAPI grouping is unchanged),
`logger = logging.getLogger(__name__)`, `from ..templating import templates`. If a helper turns out to be used
by two of the four modules, put it in `routes/_shared.py` and say so in the report; do not duplicate it.

`main.py`: replace `from .routes.pages import router as pages_router` + `app.include_router(pages_router)` with
the four imports/includes in the order given in rule 5.

Tests to update (they reach into the module for the rate-limit state):
- `tests/test_workouts_access_e2e.py:206-207` and `tests/test_workouts_wedding_boss_e2e.py:265-266`:
  `import app.backend.app.routes.auth as auth_routes` / `auth_routes._login_attempts.clear()`.

### `routes/workouts.py` → a `services/workouts/` package + a thin route module

New package `app/backend/app/services/workouts/` (`__init__.py` with only a docstring — no re-exports):

| New file | What moves there (names exactly as today) |
|---|---|
| `catalog.py` — the game's static content | `DEFAULT_EXERCISES`, `_station`, `SKILL_PROGRESSIONS`, `STATION_RENAMES`, `STATION_INDEX` and any other index built from the progressions at import time, `STATION_SESSIONS_TO_CONQUER`, `STATION_REP_FLOOR`, `PLAN_FOCUS_SETS`, `PLAN_SUPPORT_SETS`, `PLAN_SUPPORT_STATIONS`, `PLAN_SECONDS_PER_SET`, `PLAN_DURATION_SAMPLE`, `ETA_MIN_SESSIONS`, `PATHS`, `WORKOUT_TYPE_LABELS`, `station_exercise_name`, `EXERCISE_CATALOG`, `TEMPO_DEFAULT`, `TEMPO_BY_EXERCISE`, `HOLD_EXERCISES`, `WARMUP_MINUTES`, `WARMUPS`, `FORM_CUES`, `exercise_tempo`, `unit_label`, `exercise_form_data`, `TYPE_LABELS`, `LEGACY_STATION_ORDER` |
| `holo.py` — the exercises.glb reader | `HOLO_MODEL_PATH`, `HOLO_MODEL_URL`, `holo_key`, `holo_clips`, `holo_front_clips`, `holo_clip_bounds` (and the `json`/`struct`/`mimetypes` imports only they use). `HOLO_MODEL_PATH` is built from `FRONTEND_DIR`: import it with `from ...templating import FRONTEND_DIR` (`templating.py` is not a route module, so a service may depend on it; a service must never import from `routes/`). |
| `progress.py` — everything derived from saved rows | `XP_*` constants, `RANKS`, `_session_xp`, `_xp_needed_for_level`, `_level_from_xp`, `_rank_for_level`, `_next_rank_for_level`, `_total_xp_for_level`, `_rank_ladder`, `_parse_day`, `_workout_days`, `_compute_streak`, `_current_streak`, `STREAK_MILESTONES`, `_streak_details`, `_best_streak`, `_ago_label`, `_eta_label`, `compute_gamification`, `_rep_range`, `_station_for`, `_exercise_title`, `_exercise_unit`, `_best_set`, `compute_records`, `compute_paths`, `RECOVERY_STREAK_DAYS`, `plan_today`, `BOSS_*` constants, `_days_in_window`, `_pace_window`, `wedding_boss`, `_fetch_history`, `_station_progress` |
| `legacy.py` — the old browser-only flags import | `_legacy_progress_key`, `_clean_progress`, `_legacy_to_current`, `_stored_legacy_progress`, `_load_legacy_progress` |
| `admin.py` — back-office row grouping | `ADMIN_ROW_COLUMNS`, `_session_key`, `_admin_exercise`, `_group_admin_rows`, `admin_sessions`, `admin_session_rows`, `admin_session`, `admin_exercise_options`, `admin_legacy_stations` |

`routes/workouts.py` keeps: `router`, the four handlers (`workout_page`, `save_workout`, `workout_admin_page`,
`import_legacy_progress`), `SPANISH_QUEUE_IN_PAGE`, `_session_user`, `_resolve_user_id` (request-bound helpers
the API modules already import from here — leave those imports alone). It imports what it needs from
`..services.workouts.*`. A name that one new module needs from another is imported explicitly (e.g.
`progress.py` does `from .catalog import SKILL_PROGRESSIONS, STATION_INDEX, ...`). If you find a genuine
circular dependency between the new modules, stop and report it instead of inventing a workaround.

Importers to repoint (grep `routes.workouts` / `routes import workouts` across `app/` and `tests/` to be sure
this list is complete):
- `api/workouts.py`: `_clean_progress`, `_legacy_progress_key`, `_load_legacy_progress` → `services.workouts.legacy`;
  `_station_for` → `services.workouts.progress`; `admin_session`, `admin_session_rows`, `admin_sessions` →
  `services.workouts.admin`; `_resolve_user_id`, `_session_user` stay from `routes.workouts`.
- `api/push.py`, `api/spanish.py`: `_resolve_user_id` — unchanged.
- `services/push_service.py`: the three lazy `from ..routes import workouts as wk` become
  `from .workouts import progress as wk` (keep them lazy and keep the comment; it uses `_current_streak`,
  `_fetch_history`, `_workout_days`, `compute_gamification`, `compute_paths`, `plan_today`,
  `RECOVERY_STREAK_DAYS`, `_load_legacy_progress` — that last one is in `legacy`, so import it from there).
- Tests: `tests/test_workouts_e2e.py`, `tests/test_workouts_wedding_boss_e2e.py`, `tests/test_spanish_api_e2e.py`,
  `tests/test_arena_push_e2e.py` import `routes.workouts as workouts`/`wk` and use ~30 names
  (`compute_paths`, `wedding_boss`, `SKILL_PROGRESSIONS`, `exercise_form_data`, `holo_*`, `HOLO_MODEL_PATH`,
  `RANKS`, `WARMUPS`, `_station_for`, ...). Repoint each to the module that now owns the name
  (`catalog`, `holo`, `progress`, `legacy`). Do not change what the tests assert.

## Docs to update (the only non-code edits allowed)

- `CLAUDE.md` → **Project Structure** tree: replace the `pages.py` line with the four new files, add
  `templating.py`, add the `services/workouts/` package with a one-line description per file; in the
  **Authentication** section change "Rate limiting: IP-based in-memory counter in `pages.py`" to `routes/auth.py`;
  in **Workouts Module** change "derived from history in `routes/workouts.py`" to `services/workouts/progress.py`.
  Nothing else in CLAUDE.md.
- `docs/refactor/route-table-baseline.txt` stays as committed; it is the before-picture.

## Acceptance criteria

1. `routes/pages.py` no longer exists; `routes/auth.py`, `routes/home.py`, `routes/finances.py`,
   `routes/wedding.py`, `templating.py`, `services/workouts/{__init__,catalog,holo,progress,legacy,admin}.py`
   exist with the contents assigned above.
2. `grep -rn "Jinja2Templates(" app/backend/app` returns exactly one line, in `templating.py`.
3. `.venv/Scripts/python.exe -m ruff check .` → `All checks passed!`
4. `.venv/Scripts/python.exe -m pytest` → `307 passed, 1 skipped` (that is the exact baseline; one more or one
   fewer is a bug in the refactor).
5. The route table is unchanged. Regenerate it with the script below and `diff` it against
   `docs/refactor/route-table-baseline.txt`: the only acceptable output is no difference.
   ```
   PYTEST_CURRENT_TEST=1 AUTH_ENABLED=0 BUDGET_DB_PATH=<some temp file> .venv/Scripts/python.exe - <<'EOF'
   import app.backend.app.main as m
   rows = sorted((r.path, ",".join(sorted(r.methods or [])), getattr(r, "name", "")) for r in m.app.routes if hasattr(r, "methods"))
   print("# Every HTTP route the app registers: path, methods, handler name. Sorted; order of registration is not part of the contract")
   print("# (no two routes here share a path pattern with overlapping methods, so order cannot change matching).")
   for row in rows: print(*row, sep="\t")
   print("# public (auth-bypassing) route matchers:")
   for p, ms in sorted((p.pattern, ",".join(sorted(ms)) if ms else "*") for p, ms in m.PUBLIC_ROUTE_MATCHERS): print("public", p, ms, sep="\t")
   EOF
   ```
   (Run it from the repo root and strip the two `Session configuration…` / `SessionMiddleware…` lines that
   `main.py` prints on import before diffing.)
6. `git diff --color-moved=dimmed-zebra --stat` shows no template, CSS or JS file.
7. Every `@public` decorator present before is present after, on the same handler (the `public` lines in the
   baseline file are the check).

## Report

Use the four-section report from your agent instructions. In **Deviations and doubts** list every helper you
placed somewhere other than this spec says, every name you found that this spec did not list, and the exact
`diff` output of criterion 5 if it was not empty.
