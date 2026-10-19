# Refactor spec — move the inline page scripts out of the templates (phase 4)

**Kind:** pure refactor of the frontend. No behaviour change, no visual change (desktop and mobile), no new
dependency at runtime. One new dev dependency (Playwright) for the browser test that guards the move.
**Branch:** `claude/extract-page-js` (stacked on `claude/wedding-api-and-db-packages`, PR #47). You do not touch git.
**Definition of done:** the Acceptance criteria section, all of it.

## Why

Fifteen page templates carry their whole page script inline — about 4,900 lines of JavaScript inside HTML.
`wedding/guests.html` is 1,455 lines of which 551 are script; `wedding/vendors.html` 1,290 / 726. Inline scripts
cannot be linted, cached, searched as JS, or diffed without the surrounding HTML, and every edit to the page
logic is a template edit. The repo already has the right pattern (see `pages/workout.html`): server data in a
`<script type="application/json">` block, the code in `static/js/`, a `?v=` query for the service worker's
cache-first static handler.

## Rules for this refactor

1. **Move the script text verbatim.** The new `.js` file is the inline block's content, byte for byte, except
   the handful of lines that held a Jinja expression (listed below) — those become a read from the page's JSON
   data block. Nothing else changes: no reformatting, no renames, no "cleanups", no `use strict`, no module
   wrapper, no `defer`.
2. **Same position, same timing.** The `<script src=…>` tag replaces the inline block at the exact spot it
   occupied, as a plain synchronous script (no `defer`/`async`), so it runs at the same moment the inline code
   ran relative to the rest of the page and to the layout's own scripts.
3. **Server data crosses once, as JSON.** Every `{{ … }}` that was inside a script block moves into one
   `<script type="application/json" id="<page>-data">{{ {…} | tojson }}</script>` placed immediately before the
   `src` tag, and the JS reads it at the top with
   `const PAGE_DATA = JSON.parse(document.getElementById('<page>-data').textContent);`
   followed by the original assignments taking their value from `PAGE_DATA` (e.g. `const ALL_VENDORS = PAGE_DATA.vendors;`).
   Templates that already have such a block (`overseas`, `tasks`, `workout_admin`) keep it as is; only add a new
   one for the expressions still inline. `tojson` HTML-escapes `<`, so the block is safe for any content.
4. **Cache-busting.** Every new `src` carries `?v=20261019`. Say in the CLAUDE.md convention (below) that the
   value must be bumped whenever the file changes, because `sw.js` serves `/static/` cache-first by URL.
5. **No markup, CSS or Python changes** beyond the script tags and the JSON block. Inline `<style>` blocks
   stay where they are (a later phase). Hebrew UI / English code.
6. Write the browser test **first**, run it against the untouched templates, and record the result. The same
   test must pass identically after the move. That is the proof that nothing broke in the browser.

## The move

| Template (inline block lines today) | New file under `app/frontend/static/js/pages/` | Jinja expressions inside the block → `PAGE_DATA` key |
|---|---|---|
| `wedding/guests.html` (868–1418) | `wedding-guests.js` | none |
| `wedding/vendors.html` (564–1289) | `wedding-vendors.js` | `const ALL_VENDORS = {{ vendors \| tojson }};` → `vendors` |
| `wedding/seating.html` (277–929) | `wedding-seating.js` | `TABLES`, `GUESTS`, `ASSIGNS` ← `tables`, `all_guests`, `assignments` |
| `finances/transactions.html` (552–1044) | `finances-transactions.js` | none |
| `wedding/vendor_detail.html` (337–686) | `wedding-vendor-detail.js` | `const VENDOR_ID = {{ vendor.id }};` → `vendor_id`; `let quoteItems = {{ quote_items \| tojson }};` → `quote_items` |
| `wedding/milestones.html` (532–873) | `wedding-milestones.js` | `var WEDDING = {{ (view.wedding_date or '') \| tojson }};` → `wedding_date` |
| `wedding/timeline.html` (352–682) | `wedding-timeline.js` | `let allEvents = {{ events \| tojson }};` → `events` |
| `finances/transactions_import.html` (97–423) | `finances-transactions-import.js` | `var CATEGORIES = {{ categories\|tojson }};` → `categories` |
| `wedding/overseas.html` (163–483; keep the `ov-people` JSON block at 114) | `wedding-overseas.js` | none beyond the existing block |
| `wedding/tasks.html` (290–361 and 362–589 → one file, first block then second, in order; keep `task-people` at 106) | `wedding-tasks.js` | `document.getElementById('t-owner').value = {{ (me.name if me else '') \| tojson }};` → `me_name` |
| `pages/workout_admin.html` (239–498; keep `workout-admin-data` at 238) | `workouts-admin.js` | none beyond the existing block |
| `wedding/lodging.html` (243–378) | `wedding-lodging.js` | check with grep; none expected |
| `wedding/budget.html` (467–549) | `wedding-budget.js` | check with grep |
| `wedding/ideas.html` (209–337) | `wedding-ideas.js` | check with grep |
| `renovation/journal.html` (199–398) | `renovation-journal.js` | check with grep |

Confirm every line range with grep before cutting (the ranges are from the revision this spec was written
against). A block that turns out to contain a `{% … %}` tag (none were found) is a stop-and-report, not a
workaround. Not in scope: `layout/base.html`, `wedding/base.html`, `renovation/base.html` (layout shells),
`finances/index.html`, `finances/statistics.html`, `pages/workout.html` (already external).

## The browser test (write it first)

`tests/test_pages_js_browser.py`, built on the `live_server` / `browser` fixtures of
`tests/test_workouts_arena_browser.py` (copy them; the module skips itself when Playwright is missing, exactly
like that file). For each page below, at a phone viewport (393×852) and a desktop one (1280×800):

1. Open the URL, wait for `load`.
2. Assert no `pageerror` and no console message of type `error` (ignore messages about `favicon`, and about
   `cdn.jsdelivr.net` if any page loads it).
3. Assert every request for `/static/js/pages/*.js` the page made returned 200 — **after** the move; before the
   move this assertion is vacuous, which is fine.
4. Assert one page-specific element is present, proving the template rendered (e.g. the guests table container,
   the seating canvas, the transactions form). Pick an element that exists on an empty database.

Pages: `/wedding/guests`, `/wedding/vendors`, `/wedding/vendors/{id}` (create a vendor through
`POST /api/wedding/vendors` in the test with the TestClient first), `/wedding/seating`, `/finances/transactions`,
`/finances/transactions/import`, `/wedding/milestones`, `/wedding/timeline`, `/wedding/overseas`, `/wedding/tasks`,
`/workouts/admin`, `/wedding/lodging`, `/wedding/budget`, `/wedding/ideas`, and the renovation journal page
(find its path in `routes/renovation.py`). Auth is off in the test app, so no login is needed.

Run it before touching any template. If a page already logs a console error on `main`, do not "fix" the page:
put that exact message in the test's allow-list with a comment naming the page, and list it in your report.

Dev tooling for it: add `playwright==<the version now installed in .venv — check with pip show>` to
`requirements-dev.txt` under the existing comment, and add a step to `.github/workflows/ci.yml` right after
"Install": `- name: Browsers` / `run: python -m playwright install --with-deps chromium`. The browser tests then
run in CI too.

## Docs to update (the only other edits allowed)

- `CLAUDE.md` → **Project Structure**: add `pages/   # one file per page: <module>-<page>.js` under `static/js/`.
  → **Key Patterns and Conventions**: add item "**Page scripts** live in `static/js/pages/<module>-<page>.js`,
  included with a plain `<script src="…?v=YYYYMMDD">` at the end of the page's content; server data reaches
  them through one `<script type="application/json" id="<page>-data">` block read into `PAGE_DATA`. Bump `?v=`
  whenever the file changes — `sw.js` serves `/static/` cache-first by URL. No inline `<script>` in page templates."
  Nothing else in CLAUDE.md.

## Acceptance criteria

1. The fifteen templates contain no inline `<script>` block other than `type="application/json"` ones:
   `grep -c "<script>" app/frontend/templates/{wedding,finances,renovation,pages}/*.html` is 0 for every
   template in the table (other templates are untouched).
2. Fifteen files exist under `app/frontend/static/js/pages/` with the names above, and `node --check` passes on
   each (Node is installed on this machine).
3. For each file, `diff` between the new file and the inline block it came from (the old lines are in
   `git show HEAD:<template>`) shows only the `PAGE_DATA` lines described in rule 3 — paste the per-file diff
   line counts in your report (expected: 0 for the pages with no Jinja, 2–4 for the others).
4. `tests/test_pages_js_browser.py` passes before the move (with the allow-list, if any) and after it, in
   `.venv/Scripts/python.exe -m pytest tests/test_pages_js_browser.py`.
5. `.venv/Scripts/python.exe -m pytest` → everything that passed before still passes: the Playwright suites now
   run in `.venv` (Playwright is installed there), so the count is `316 passed` or more, 0 failed.
6. `.venv/Scripts/python.exe -m ruff check .` → `All checks passed!`
7. `tools/refactor_baseline.py routes` still matches `docs/refactor/route-table-baseline.txt` (nothing in
   Python changed, so this is a sanity check).
8. `git status` shows no change under `app/backend/`.

## Report

The four-section report. In **Deviations and doubts**: the per-file diff counts (criterion 3), the console-error
allow-list with the page each entry belongs to, any Jinja expression this spec did not list, and anything about
timing or load order you were not sure about.
