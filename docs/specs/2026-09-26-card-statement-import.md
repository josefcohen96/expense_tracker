# דוח האשראי — card-statement-import

**Date:** 2026-09-26 · **Module:** finances · **Who:** Yosef & Karina

## In one line
Once a month, when the Max credit-card statement (`transaction-details_export_*.xlsx`) lands in the mailbox, Yosef or Karina drop it on the app and only the charges the app does not already have are added, each with a category the app already learned, and one undo pill.

## The signature
The app already knows three things a generic importer does not: **whose card it is** (the holder's name in cell A1 is matched to the household's Hebrew display names), **which charges it booked itself** (rows materialised by a recurrence match by amount within a few days, because a subscription's `day_of_month` is never exactly the card date), and **how each merchant was filed last time** (the newest transaction whose notes equal the merchant name lends its category, so correcting "WOLT" once teaches the next statement). Nothing new is stored: notes carry the merchant, and every decision is derived from the rows that already exist.

## Framings considered
- A (straight): an "Import CSV" page with a column mapper and a confirm dialog — lost because it asks the user to explain the file, and Max already tells us everything.
- B (house style): recognise the Max layout, recognise the payer, skip what recurrences already booked, learn categories from notes, undo instead of confirm — chosen.
- C (subtraction): forward the mail to the app and import silently with no screen at all — lost for now because a first import with unknown merchants needs a place to correct categories; it becomes possible once the merchant memory has filled up (see Out of scope).

## Behaviour

### Entry points
- **Transactions page** (`/finances/transactions`), the filter card's action row: a fourth button `טען דוח אשראי` (icon `fa-file-import`, `btn btn-outline btn-sm`) after `ייצא לאקסל`, linking to `/finances/transactions/import`. The row's grid becomes `sm:grid-cols-4`. This is the one desktop change and it is intended: the file is dropped from a computer as often as from a phone.

### The page `/finances/transactions/import` — title `דוח האשראי`
Extends `finances/base.html` (sidebar highlight stays on `עסקאות`, since the path contains `transactions`). Three states, all on one page, driven by vanilla JS in the template (`backup.html` is the model for a JS-driven finances page).

**State 1 — pick a file.** A card with a large drop zone (`דוח מקס (xlsx) — גרור לכאן או לחץ לבחירה`), an `<input type="file" accept=".xlsx">`, and one line of help: `הדוח החודשי שמגיע במייל מ-max. נוסיף רק עסקאות שעוד לא רשומות.` Choosing or dropping a file immediately posts it to the preview API (no extra button). While waiting: `קורא את הדוח…`.

**State 2 — preview.** Rendered from the preview response.
- Header line: `{{ holder }} · כרטיס {{ card_last4 }} · {{ statement_month }}` (each part only if known).
- A payer select `מי שילם` pre-set to the guessed `user_id`; an account select `חשבון` pre-set to the account named `כרטיס אשראי` (or empty if it does not exist). Both apply to every added row.
- **Every row is the user's call.** Each line has a checkbox, the date as `DD.MM`, the merchant name as a text input, the amount as a number input (`dir="ltr"`, statement charge, positive), and a category `<select>` pre-set to `category_id`. Typing in a field ticks the row. An amount that is empty, not a number or zero is outlined red and left out of the count until fixed.
- **New rows** (`status == "new"`), heading `חדשות ({{ n }})`, come checked. Under the select, a small caption when `category_source == "merchant"`: `כמו בפעם הקודמת`; when `"fallback"`: `לא זוהתה קטגוריה` in amber. Rows with `category_source == "fallback"` sort first so the ones needing a look are at the top; the rest keep file order.
- **Skipped rows**, a collapsed `<details>` with summary `כבר רשומות ({{ n }})` and the hint `סמן שורה כדי להוסיף אותה בכל זאת`: the same editable line, unchecked, with the reason under the select: `קיימת` for `"exists"`, `הוצאה קבועה` for `"recurring"`. Ticking one adds it anyway.
- Primary button at the bottom (full width on mobile): `הוסף {{ checked }} עסקאות` — the count follows the checkboxes of both lists and uses the edited values; disabled at zero. When there are no new rows the new list shows `הכל כבר רשום 🙌`; the button stays, since a skipped row may still be ticked.
- Mobile (< lg): each new row is a two-line card (date · merchant · amount on the first line, the category select on the second). Desktop: the same list; no table.

**State 3 — done.** After the import responds: `נוספו {{ count }} עסקאות` with a link `לעסקאות של {{ statement_month }}` to `/finances/transactions?date_from=<min date>&date_to=<max date>` (the dates of the added rows), and a toast via `window.AppToast('נוספו N עסקאות', 'ביטול', undo)` where `undo` calls the undo API with the returned ids and then shows `בוטל`. When `AppToast` is not present (desktop has no tab-bar toast), the page renders an inline `ביטול` button next to the summary that does the same. After a successful undo the page returns to state 1.

**Errors.** A file that is not a Max statement (no header row found in any sheet) → the preview API answers 400 with `detail: "הקובץ לא נראה כמו דוח של max"` and the page shows that text under the drop zone, staying in state 1. Any other failure: `שגיאה בקריאת הקובץ`.

### Matching rules ("scan by date, add only what is missing")
Applied to the file's rows in file order, against the transactions in `[min file date − 3 days, max file date + 3 days]`, each existing row usable once:
1. **exists** — an existing transaction (recurring or not) with the same `date` and the same absolute amount (compared at two decimals).
2. **recurring** — otherwise, an existing transaction with `recurrence_id IS NOT NULL`, the same absolute amount, and a date within ±3 days.
3. **new** — otherwise.
Two identical rows in the file with one match in the DB → one `exists`, one `new` (multiset matching).

### Category guess, in order
1. `merchant` — the newest transaction (`ORDER BY date DESC, id DESC`) whose `notes` equal the normalised merchant name → its `category_id`.
2. `map` — `MAX_CATEGORY_MAP` (Max's `קטגוריה` column → ordered app category names); the first name that exists in `categories` wins. Initial map:
   - `מסעדות, קפה וברים` → אוכל בחוץ
   - `מזון וצריכה` → הוצאות בית
   - `דלק, חשמל וגז` → רכב
   - `תחבורה ורכבים` → תחבורה
   - `שירותי תקשורת`, `חשמל ומחשבים`, `עירייה וממשלה`, `ביטוח` → הוצאות בית
   - `פנאי, בידור וספורט`, `אופנה`, `תיירות ונופש`, `טיסות` → פנאי
   - `בריאות`, `רפואה`, `בתי מרקחת` → בריאות
3. `fallback` — `הוצאות בית` if it exists, else the first category that is neither income (`INCOME_CATEGORIES` in `api/transactions.py`) nor `is_saving`.

### Payer guess
`holder` is the text before the first `-` in the first non-empty cell above the header row (Max writes `יוסף כהן-<id>`). Its first word is compared with `display_name()` of each household member (`people.household`); a match gives `user_id`. No match → the logged-in user's household entry (`people.find_person`), else the first household member.

## Data
No schema change. Imported rows are ordinary transactions: `date` = the file's `תאריך עסקה` (ISO), `amount` = `-(סכום חיוב)` (a negative charge on the statement, i.e. a refund, therefore becomes a positive row), `category_id`, `user_id`, `account_id` (the chosen account or NULL), `notes` = the normalised merchant name, `tags` NULL, `recurrence_id` NULL.

Normalised merchant name: whitespace collapsed to single spaces and stripped (`"IHERB IHERB.COM        IHERB.COM     NL"` → `"IHERB IHERB.COM IHERB.COM NL"`).

New service `app/backend/app/services/card_statement.py`:
- `parse_statement(data: bytes) -> dict` — opens the workbook with openpyxl (`read_only=True, data_only=True`), walks every sheet, finds the header row as the first row containing both `תאריך עסקה` and `סכום חיוב`, maps columns by header text (`שם בית העסק`, `קטגוריה`, `4 ספרות אחרונות של כרטיס האשראי`, `מטבע חיוב`, `תאריך חיוב`, `הערות`), and reads rows until the first row whose date cell is empty. Dates accept `DD-MM-YYYY`, `DD/MM/YYYY`, `YYYY-MM-DD` and datetime cells; a row whose date does not parse is skipped. Cells above the header: the first non-empty string is `holder`, the first string matching `^\d{2}/\d{4}$` is `statement_month`, `card_last4` comes from the first data row's column. Raises `ValueError` when no sheet has a header row. Returns `{"holder", "statement_month", "card_last4", "rows": [{"date", "merchant", "amount", "max_category", "sheet"}]}`.
- `classify(conn, rows) -> list[dict]` — the matching rules above; adds `status` and `matched_id`.
- `guess_category(conn, merchant, max_category, categories) -> (category_id, source)` and `guess_payer(conn, holder, session_user) -> user_id`.
- `MAX_CATEGORY_MAP` lives here.

## API
All under `api/transactions.py` (same router, same access rules as the rest of `/api/transactions`):

- `POST /api/transactions/import/preview` — multipart `file`. Response:
  ```json
  {"holder": "יוסף כהן", "statement_month": "09/2026", "card_last4": "4022",
   "user_id": 1, "account_id": 2,
   "rows": [{"index": 0, "date": "2026-08-15", "merchant": "WOLT", "amount": 205.9,
             "max_category": "מסעדות, קפה וברים", "status": "new", "matched_id": null,
             "category_id": 9, "category_source": "merchant"}],
   "counts": {"new": 17, "exists": 6, "recurring": 2}}
  ```
  `amount` is the statement's charge (positive for a charge). 400 with the Hebrew detail above when parsing fails.
- `POST /api/transactions/import` — JSON `{"user_id", "account_id" | null, "rows": [{"date", "amount", "merchant", "category_id"}]}`. Inserts each row as described under Data, invalidates `top_expenses_3months` and `statistics_full`, returns `{"created": [ids], "count": n, "date_from": "...", "date_to": "..."}`. 400 when `rows` is empty or a `category_id` / `user_id` does not exist.
- `POST /api/transactions/import/undo` — JSON `{"ids": [...]}`. Deletes those transactions where `recurrence_id IS NULL`, invalidates the same cache keys, returns `{"deleted": n}`.

Pydantic models go in `schemas/transactions.py` (`ImportRow`, `ImportRequest`, `ImportUndoRequest`).

## Files to touch
- `app/backend/app/services/card_statement.py` — new: parsing, matching, category and payer guesses, `MAX_CATEGORY_MAP`.
- `app/backend/app/api/transactions.py` — the three import endpoints (import `UploadFile, File`).
- `app/backend/app/schemas/transactions.py` — the import request models.
- `app/backend/app/routes/pages.py` — `GET /finances/transactions/import` rendering `finances/transactions_import.html` with `categories` (expense ones only, same filter as the transactions page), `users` (household), `accounts`.
- `app/frontend/templates/finances/transactions_import.html` — new page, three states, vanilla JS.
- `app/frontend/templates/finances/transactions.html` — the `טען דוח אשראי` button in the filter action row.
- `tests/test_card_import_e2e.py` — new; builds a Max-shaped workbook with openpyxl in the test (never commit the real statement: it carries the holder's ID number).

## Acceptance criteria
1. Preview of a Max-shaped workbook with two sheets (header on row 4, three title rows, blank row + `סך הכל` + total after the data) returns every data row from both sheets, with ISO dates, positive amounts, `holder`, `statement_month` and `card_last4`.
2. A file row whose date and absolute amount equal an existing transaction is `exists`; a row whose amount equals a recurrence-materialised transaction dated within ±3 days is `recurring`; everything else is `new`.
3. Two identical file rows against one matching transaction yield one `exists` and one `new`.
4. `category_source == "merchant"` and the learned `category_id` when a transaction exists whose notes equal the merchant; `"map"` for a mapped Max category otherwise; `"fallback"` otherwise.
5. `user_id` in the preview is the household member whose display name is the holder's first word (`יוסף` → Yosef, `קארינה` → Karina); an unknown holder falls back without error.
6. Import creates exactly the posted rows with negative amounts, `notes` = merchant, the given user/account/category, and a second preview of the same file then reports them all as `exists` (idempotent re-upload).
7. Undo with the returned ids deletes them and nothing else; a recurrence-materialised id in the list is left alone.
8. A workbook with no recognisable header → 400 with the Hebrew detail.
9. `GET /finances/transactions/import` is 200 and contains `דוח האשראי`; `GET /finances/transactions` contains a link to `/finances/transactions/import`.
10. Desktop transactions page is unchanged except for the added button in the filter action row.

## Tests to add
`tests/test_card_import_e2e.py`, using `app_client` and `db_conn` from `conftest.py`, with a helper `_max_workbook(rows_by_sheet)` that writes the Max layout to `BytesIO`:
- `test_preview_parses_both_sheets` — criterion 1.
- `test_preview_marks_existing_and_recurring` — criterion 2 (insert one plain transaction and one row with a `recurrence_id`/`period_key` via SQL for a recurrence created through `POST /api/recurrences`; clean up).
- `test_preview_multiset_matching` — criterion 3.
- `test_preview_category_sources` — criterion 4.
- `test_preview_guesses_payer_from_holder` — criterion 5.
- `test_import_then_repreview_is_idempotent` — criterion 6.
- `test_undo_deletes_only_imported` — criterion 7.
- `test_preview_rejects_unknown_file` — criterion 8.
- `test_import_page_and_link` — criterion 9.

## Part 2 — from the mailbox, by itself (Google Apps Script)

The statement arrives by mail; a free Google Apps Script (`tools/gmail_max_import.gs`) runs once a day in Yosef's Gmail, finds the Max mail with the xlsx attachment, and posts it to the app. The app does the same work as the page (parse, match, learn categories) and adds only the new rows, without anyone looking. The script then labels the mail `max-imported` so it is never posted twice, and mails a one-line summary with a link to the month's transactions.

### API
`POST /api/transactions/import/auto` — multipart `file`, marked `@public` (from `..auth`) so no session is needed. Guarded by a dedicated token instead:
- The env var `IMPORT_TOKEN` holds the token. When it is unset or empty the endpoint answers 403 `detail: "ייבוא אוטומטי כבוי"` for every caller, before reading the file.
- The request must carry `Authorization: Bearer <token>`; compared with `hmac.compare_digest`. Missing or wrong → 401 `detail: "אסימון לא תקין"`. Nothing else in the response distinguishes the two.
- Otherwise: `parse_statement` (400 with the same Hebrew detail as the preview when it fails), `classify`, `guess_category` with `_import_categories`, payer = `guess_payer(conn, holder, None)` (holder name, else the first household member), account = `כרטיס אשראי` if it exists. Every row with `status == "new"` is inserted exactly as `POST /api/transactions/import` inserts (reuse one helper for the INSERT + cache invalidation so the two paths cannot drift). Rows whose `category_source == "fallback"` are still added (the summary counts them so Yosef can fix them on the transactions page).
- Response: `{"added": n, "skipped": {"exists": n, "recurring": n}, "unsorted": n, "created": [ids], "holder", "statement_month", "date_from", "date_to"}` (`date_from`/`date_to` are the min/max date of the added rows, `null` when nothing was added). Posting the same file again adds 0.

### Files to touch
- `app/backend/app/api/transactions.py` — the endpoint, `@public`, token check, shared insert helper.
- `tools/gmail_max_import.gs` — the Apps Script (written in the main session, not by the implementer).
- `CLAUDE.md` — one row in the environment-variable table for `IMPORT_TOKEN` (main session).
- `tests/test_card_import_e2e.py` — the tests below.

### Acceptance criteria
11. With `IMPORT_TOKEN` unset, `POST /api/transactions/import/auto` is 403 even with a well-formed file and header.
12. With `IMPORT_TOKEN` set, a missing or wrong bearer token is 401 and nothing is inserted.
13. With the right token, the new rows of a Max-shaped workbook are inserted (negative amounts, notes = merchant, payer from the holder), the response counts match, and a second post of the same file adds 0 with every row counted under `skipped.exists`.
14. The route is registered as public: `build_public_route_matchers(app)` contains a matcher for `/api/transactions/import/auto` with `POST`.

### Tests to add
- `test_auto_import_disabled_without_token`, `test_auto_import_rejects_bad_token`, `test_auto_import_adds_only_new_and_is_idempotent`, `test_auto_import_route_is_public` — criteria 11–14. Set and clear `IMPORT_TOKEN` with `monkeypatch.setenv` / `monkeypatch.delenv` so the suite order does not matter.

## Out of scope
- A share target on the phone (needs `display: standalone` in the manifest).
- Other card companies' layouts; only the Max export is recognised.
- Editing dates or amounts in the preview; the transactions page already edits inline.
- A Web Share Target in the manifest (needs `display: standalone`, which changes how the whole app installs).

## Open questions
None — implement as written.
