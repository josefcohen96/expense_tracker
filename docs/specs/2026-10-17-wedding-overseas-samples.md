# הזמנות מחו״ל — wedding-overseas-samples

**Date:** 2026-10-17 · **Module:** wedding · **Who:** Yosef & Karina, on the phone

## In one line
Everything they want to order from abroad for the wedding (favours, decor, signage…) goes on one page where each item is first tested as a single sample — wanted → ordered → arrived → verdict — with a comment thread between the two of them, and a deadline, derived from the wedding date, by which the big order has to leave.

## The signature
**The big order has a date, and the app already knows it.** A banner at the top says `ההזמנה הגדולה צריכה לצאת עד 4 במאי · בעוד 41 ימים`, computed as the wedding date minus a lead time (default 6 weeks, a wedding setting). Every sample on its way shows how long ago it was ordered, so a glance tells them whether there is still time to test a second one. Moving an item forward is one tap (`הזמנתי דוגמה`, `הגיע!`, ✅ / ❌) with an undo pill, never a confirm. When a sample is approved, the quantity field suggests the headcount, and the approved lane adds up what the big order will roughly cost from the sample prices.

## Framings considered
- A (straight): a page listing items with name, link, status dropdown, notes textarea — lost because a status dropdown on a phone is three taps and no one would know when the order has to go out.
- B (house style): a sample moves through lanes with one-tap advances and undo, a comment thread with the two avatars, and the big-order deadline anchored to the wedding date — **chosen**.
- C (subtraction): a `הזמנות מחו״ל` category on the existing רעיונות page, reusing its statuses and description as the comment field — lost because ideas have no "ordered on / arrived on" dates, no per-comment author, and the user explicitly asked for comments and a dedicated section.

Stolen along the way: the messaging app's thread (comments as a chat between Yosef and Karina), the board game's lanes (an item physically moves forward), the calendar's deadline, the bank statement's `× quantity ≈ total`.

## Behaviour

New page `GET /wedding/overseas`, title `הזמנות מחו״ל`, extends `wedding/base.html`. Household only (the existing `/wedding` prefix rules in `services/access.py` already cover it; nothing to add there).

### Navigation
- **Mobile:** add `('מחו״ל', '/wedding/overseas')` to the `planning` section chips in `wedding/base.html` (after `רעיונות`). The section header then highlights `תכנון` on this page.
- **Desktop:** add a sidebar link `הזמנות מחו״ל` to the wedding sidebar in `wedding/base.html`, after `רעיונות`, same markup as the neighbours (icon: a parcel/box path). This is the only change to an existing desktop screen, and it is required for the page to be reachable.

### Header action
`{% block wedding_header_action %}` holds the primary button `+ פריט` marked `data-quick-add="+ פריט"` (it is lifted into the mobile section header like the other wedding pages). It opens the item sheet.

### The deadline banner (top of page)
Rendered only when a wedding date exists and the deadline is today or later:
- Line 1: `ההזמנה הגדולה צריכה לצאת עד {{ long_date }}`
- Line 2: `{{ in_days_label(days_left) }} · {{ lead_weeks }} שבועות לפני החתונה`
- A small `שינוי` link that reveals an inline number input (weeks, 1–20) saving `overseas_lead_days = weeks*7` through the existing `POST /api/wedding/settings`; the banner re-renders on reload.
When the deadline has passed but the wedding is still ahead: same banner, line 2 reads `{{ overdue_label(-days_left) }}` in the overdue colour. No wedding date → no banner, no placeholder.

### Lanes (in order, each a section with a title and a count)
1. `לבדוק` — stage `to_order`. Items they want to try. Row action: `הזמנתי דוגמה`.
2. `בדרך` — stage `ordered`. Meta: `הוזמנה {{ ago_label }}` (`היום` / `אתמול` / `לפני יומיים` / `לפני N ימים` / `לפני N שבועות`). Row action: `הגיע!`.
3. `הגיע — מה דעתכם?` — stage `arrived`. Meta: `הגיעה {{ ago_label }}`. Two row actions: `✅ להזמנה הגדולה`, `❌ לא מתאים`.
4. `להזמנה הגדולה` — stage `approved`. Meta: `× {{ quantity_needed }}` and `≈ ₪{{ estimate }}` when the item has both a sample price and a quantity. Lane footer when at least one item has an estimate: `סה״כ משוער: ₪{{ sum }}`. Row action: `בסוף לא` (moves to `rejected`).
5. `נפסל` — stage `rejected`, rendered dimmed (opacity like `.tb-row.is-done`). Row action: `חזרה לבדיקה` (back to `to_order`).

Empty lanes are hidden except `לבדוק`, which shows `אין כאן פריטים לבדיקה` when empty. Whole page empty: an empty state with 📦, `עדיין לא הזמנתם כלום מחו״ל`, `כל מה שרוצים לנסות לפני ההזמנה הגדולה — דוגמה אחת קודם`, and a button `הוסף פריט ראשון`.

### Row
Each row (reuse the `.tb-row` / `.tb-row-inner` visual language from the task board, new class prefix `.ov-`):
- Title (bold), optional store chip (`AliExpress`, `Temu`, free text), meta line as above.
- Comment count bubble `💬 3` when > 0.
- The stage action button(s) on the end side.
- Tapping the row body expands it in place (accordion, one open at a time) showing: the link (`פתיחה בחנות ↗`, opens in a new tab, only when `url` set), `דוגמה: ₪{{ sample_price }}`, `כמות להזמנה: {{ quantity_needed }}`, an `עריכה` button, and the **comment thread**.

### Stage changes and undo
Every stage action is optimistic: the row moves to the target lane immediately, lane counts update, `PUT /api/wedding/overseas/{id}` is sent with `{"stage": ...}`, and `window.AppToast` shows `הפריט עבר ל{{ lane }}` with action `ביטול` for 4 seconds that sends the previous stage back. The server sets `ordered_at` / `arrived_at` (see Data) so the undo restores them too. On a failed request the row snaps back and the toast says `שגיאה בשמירה`.

### Comment thread (inside the expanded row)
- Comments oldest first: the author's avatar (`avatar()` macro from `layout/_mobile_nav.html`, 24px; a neutral grey circle `?` when author is null), the body, and `relative_day(created_at)`.
- A one-line input `הערה…` with a send button `שלח` (also Enter). Posting is optimistic with the logged-in person as author; the comment is appended and the count bubble increments. Empty bodies are ignored.
- Comments are immutable in this version (no edit, no delete).

### Item sheet (add / edit)
A bottom sheet on mobile, centred modal on `lg` (same construction as the ideas modal: fixed overlay, card, `max-h-[92vh]`):
- `שם הפריט` (required), `קישור` (url, optional), `חנות` (chips `AliExpress` · `Temu` · `Shein` · `Amazon` · `אחר` with a free-text field under `אחר`), `מחיר הדוגמה (₪)` (number, optional), `כמות להזמנה הגדולה` (number, optional) whose placeholder is `למשל {{ headcount.people }} — כמו מספר המוזמנים` when headcount > 0, else `כמות`.
- Primary `שמירה`; new items land in `לבדוק`. Save reloads the page (same as the ideas page; the list is server-rendered).
- Edit mode adds a `מחיקה` text button: the row is hidden at once, a toast `הפריט נמחק` with `ביטול` for 4 seconds; the `DELETE` is sent only when the toast expires (and on `pagehide` via `fetch(..., {method:'DELETE', keepalive:true})`). `ביטול` just un-hides the row.

### Desktop
Same single-column page, `max-w-3xl mx-auto`; the sheet becomes a centred modal. No other desktop page changes beyond the sidebar link.

## Data

**New tables** (inline `CREATE TABLE IF NOT EXISTS` in `initialise_database()`, per the `db-migration` skill):

```sql
CREATE TABLE IF NOT EXISTS wedding_overseas_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    url TEXT,
    store TEXT,
    sample_price REAL,
    quantity_needed INTEGER,
    stage TEXT NOT NULL DEFAULT 'to_order',
    ordered_at TEXT,
    arrived_at TEXT,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS wedding_overseas_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES wedding_overseas_items(id) ON DELETE CASCADE,
    author TEXT,
    body TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

`created_by` / `author` hold a `users.name` validated with `people.valid_owner` (unknown name → 422), or NULL.

**Setting:** `wedding_settings.overseas_lead_days` (string integer, default when absent: `42`). Validate in `upsert_setting`: digits only, 7 ≤ value ≤ 140 → otherwise 422 `זמן אספקה חייב להיות בין שבוע ל-20 שבועות`.

**Derived, never stored** — new service `services/overseas.py`:
- `STAGES = ("to_order", "ordered", "arrived", "approved", "rejected")`, `STAGE_LABELS` (the Hebrew lane names above).
- `deadline(conn, today) -> Optional[dict]`: `{"date", "label" (long_date), "days_left", "days_label" (in_days_label / overdue_label), "lead_days", "lead_weeks"}` from `wedding_plan.get_wedding_date` and the setting; `None` without a wedding date.
- `estimate(item) -> Optional[float]`: `sample_price * quantity_needed` when both are set and positive, else `None`.
- `decorate(item, today) -> dict`: adds `ordered_ago`, `arrived_ago` (via the new `hebrew_dates.ago_label`), `estimate`, `estimate_label` (`₪1,200`, thousands-separated, no decimals), `comment_count`.
- `lanes(items) -> list[dict]`: `[{"key", "label", "items", "estimate_total"}]` in `STAGES` order.
- `stage_transition(existing_row, new_stage, today) -> dict`: the columns to write. Moving to `ordered` sets `ordered_at = today` if null; to `arrived` sets `arrived_at = today` if null (and `ordered_at = today` if still null); to `to_order` clears both; to `ordered` from a later stage clears `arrived_at`. `approved` / `rejected` leave dates untouched.

**New helper** `hebrew_dates.ago_label(d: date, today: date) -> str`: `היום`, `אתמול`, `לפני יומיים`, `לפני N ימים` (< 14), `לפני שבועיים`, `לפני N שבועות` (< 60), `לפני N חודשים`.

Headcount for the quantity placeholder comes from `wedding_plan.headcount(conn)` (already exists). No `cache_service` involvement (it caches statistics only).

## API

All under the existing `wedding_api` router (`/api/wedding`), household access as today. Pydantic models in `schemas/wedding_overseas.py` (new file; the wedding router currently keeps its models inline, so put these in the router module next to `IdeaCreate` if that is the convention there — follow the file).

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/overseas` | — | `{"deadline": {...}|null, "lanes": [...]}` with each item decorated and carrying its `comments` list |
| POST | `/overseas` | `{title (1–200, required), url?, store?, sample_price? ≥0, quantity_needed? ≥0 int, created_by?}` | 201, the decorated item. `created_by` defaults to the session user's name when present |
| PUT | `/overseas/{id}` | any subset of `title, url, store, sample_price, quantity_needed, stage` | 200 decorated item; 404 unknown id; 422 stage not in `STAGES`. A `stage` change applies `stage_transition` |
| DELETE | `/overseas/{id}` | — | 204; comments cascade (`PRAGMA foreign_keys = ON` is already set) |
| POST | `/overseas/{id}/comments` | `{body (1–2000), author?}` | 201 `{id, item_id, author, body, created_at}`; author defaults to the session user, validated with `valid_owner` |

Session user in the API: `getattr(request.state, "user", None) or request.session.get("user")`, the same expression `api/today.py` uses.

## Files to touch
- `app/backend/app/db.py` — the two `CREATE TABLE IF NOT EXISTS` statements next to `wedding_ideas`.
- `app/backend/app/services/overseas.py` — **new**, the derived logic above.
- `app/backend/app/services/hebrew_dates.py` — `ago_label`.
- `app/backend/app/api/wedding.py` — the five routes, models, `overseas_lead_days` validation in `upsert_setting`.
- `app/backend/app/routes/pages.py` — `GET /wedding/overseas` rendering `wedding/overseas.html` with `deadline`, `lanes`, `people`, `me`, `headcount`, `stages`.
- `app/frontend/templates/wedding/overseas.html` — **new**: banner, lanes, rows, thread, sheet, inline script (vanilla, like `tasks.html`).
- `app/frontend/templates/wedding/base.html` — mobile chip + desktop sidebar link.
- `app/frontend/static/css/main.css` — `.ov-*` classes (banner, lane title, row, thread, sheet) in the task-board visual language, rose accents.
- `tests/test_wedding_overseas_e2e.py` — **new**.

## Acceptance criteria
1. `GET /wedding/overseas` returns 200 and contains `הזמנות מחו״ל`; `GET /wedding/tasks` contains a link to `/wedding/overseas`.
2. `POST /api/wedding/overseas` with a title creates an item in stage `to_order` with `ordered_at` and `arrived_at` null; it appears in the `לבדוק` lane of the page.
3. `PUT stage=ordered` sets `ordered_at` to today; then `PUT stage=arrived` sets `arrived_at` to today and keeps `ordered_at`; `PUT stage=approved` leaves both; `PUT stage=to_order` clears both.
4. `PUT stage=flying` → 422. `PUT` on an unknown id → 404.
5. With wedding date `2030-06-15` and no lead setting, `deadline()` is `2030-05-04` with `lead_weeks == 6`; after `POST /api/wedding/settings {overseas_lead_days: "28"}` it is `2030-05-18`; `overseas_lead_days: "3"` → 422; with no wedding date the API returns `deadline: null` and the page has no `ההזמנה הגדולה` text.
6. `sample_price 8, quantity_needed 150` → `estimate == 1200` and `estimate_label == "₪1,200"`; an item missing either has `estimate None`; the approved lane's `estimate_total` sums only approved items.
7. `POST /overseas/{id}/comments {body: "קטן מדי", author: "Karina"}` → 201 with author `Karina`; the item's `comment_count` becomes 1 and the page shows `קטן מדי`; `author: "Someone"` → 422; empty body → 422.
8. `DELETE /overseas/{id}` → 204 and its comments are gone from `wedding_overseas_comments`.
9. `ago_label`: today → `היום`, 1 → `אתמול`, 2 → `לפני יומיים`, 5 → `לפני 5 ימים`, 14 → `לפני שבועיים`, 21 → `לפני 3 שבועות`.
10. Full test suite: no new failures beyond the pre-existing ones.

## Tests to add
`tests/test_wedding_overseas_e2e.py` (restore the wedding date like `test_wedding_milestones_e2e.py` does; delete created items in fixtures):
- `test_overseas_page_renders_and_is_linked`
- `test_item_starts_in_to_order_lane`
- `test_stage_transitions_set_and_clear_dates`
- `test_invalid_stage_and_unknown_id`
- `test_deadline_derives_from_wedding_date_and_lead_setting`
- `test_estimate_and_approved_total`
- `test_comment_thread_and_author_validation`
- `test_delete_cascades_comments`
- `test_ago_label`

## Out of scope
Editing or deleting comments; photos of the sample; tracking numbers or carrier lookups; surfacing the deadline on היום or as a milestone row; a vendor record for the store; currency conversion; drag-and-drop between lanes; notifications. Nothing changes on `/wedding` (overview) or any finances page.

## Open questions
None — implement as written. Defaults chosen: lead time 6 weeks; store chips AliExpress · Temu · Shein · Amazon · אחר.
