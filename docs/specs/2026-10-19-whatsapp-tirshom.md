# תרשום — whatsapp-tirshom

**Date:** 2026-10-19 · **Module:** shell (finances + wedding) · **Who:** Yosef & Karina, each from their own phone, inside WhatsApp

## In one line
A WhatsApp number the household texts the way they would text each other — `350 פרחים` records an expense, `להתקשר לצלם עד חמישי` adds a wedding task, `סיימתי צלם` closes one — and the bot answers in one line that ends with the number that matters (this month's spend, or the countdown to the wedding).

## The signature
**The phone number is the login.** Nobody signs in, picks a payer, or picks an account: a message from Karina's phone is a Karina expense on כרטיס אשראי, the same message from Yosef's phone is a Yosef expense on מזומן (`people.DEFAULT_ACCOUNT_BY_USER`). That is why two words are a complete expense. There are no slash commands and no "are you sure": the bot does the thing and the next message can say `בטל`, the chat version of the app's undo pill. Every expense reply closes with `הוצאות החודש: ₪8,420`; every task reply closes with `עוד 12 שבועות ו-3 ימים לחתונה`.

## Framings considered
- A (straight): a menu bot — "1 להוצאה, 2 למשימה", then "סכום?", then "קטגוריה?", or `/expense 350 flowers`. Lost because it is a phone IVR: three round-trips per expense, and slash commands are English in a Hebrew chat.
- B (house style): no command words for the two common things (a number means money, a sentence means a task); the sender is the payer / the owner; replies end in the household's own number; `בטל` instead of confirm. **Chosen.**
- C (subtraction): no bot — put the existing quick-add sheet behind an iOS/Android share target or a home-screen shortcut. Lost because it still means leaving WhatsApp and opening the app; the user explicitly wants to type where they already are. One piece survives: the bot has **no UI at all** in the app, mobile and desktop stay pixel-identical.

Calendar: due dates are written as weekdays (`עד חמישי`) and shown relative to today (`hebrew_dates.due_label`). Messaging app: every reply is sent as a WhatsApp reply to the message it answers (`context.message_id`), so a burst of five messages threads cleanly. Board game: "taking" a task (`לקחתי 3`) reads like picking up a card. Bank statement: the running month total after each expense.

Not an LLM: the grammar below is a dozen deterministic rules, free, offline, and unit-testable. Free-text dates or receipts via photo could be added behind the same `handle_message()` later.

## Behaviour

No screens. Everything happens in a WhatsApp chat with the household's business number (Meta WhatsApp Cloud API, see **API → Provider setup**). The bot only talks to the two phones listed in `WHATSAPP_PHONE_YOSEF` / `WHATSAPP_PHONE_KARINA` (digits as WhatsApp sends `wa_id`, e.g. `9725xxxxxxxx`). A message from any other number is logged at WARNING and **ignored, with no reply** (the bot must not reveal that it exists). A non-text message (image, audio, sticker, reaction) from a known phone gets `אני מבין רק טקסט בינתיים 🙂`.

Mobile (< lg) and desktop: **unchanged**. No template, CSS or JS changes.

### Normalisation (before every rule)
Trim; collapse whitespace; strip trailing `.`/`!`; remove `₪`, `ש"ח`, `ש״ח`, `שח`, `שקל`, `שקלים` as standalone tokens or amount prefixes/suffixes; thousands separators `1,200` → `1200`. Matching of command words is case-insensitive and ignores a trailing `:`.

### Dispatch order (first match wins)
1. **Undo** — the whole message is `בטל` / `ביטול` / `בטל!`.
2. **Help** — `עזרה` / `?` / `help` / `מה אפשר`.
3. **List** — `משימות` / `רשימה` / `מה יש` / `מה נשאר` → all open tasks. `שלי` / `המשימות שלי` → open tasks whose owner is the sender.
4. **Done** — first word in {`סיימתי`, `בוצע`, `עשיתי`, `גמרתי`, `סגרתי`, `✓`, `✅`, `v`}; the rest is a task reference (below).
5. **Take** — starts with `לקחתי` / `אני על זה` / `אני אעשה`; the rest is a task reference.
6. **Expense** — the message does **not** contain `עד ` followed by a date-ish token, and its first or last token is an amount: `\d+(?:[.,]\d{1,2})?`, 0 < amount < 1,000,000.
7. **Task** — anything else with two or more words. A single word that matched nothing → the help text prefixed by `לא הבנתי.`.

**Task reference** (rules 4–5): a bare integer is a task id (`#3` and `3` both work); anything else is a case-insensitive substring of an **open** task's title. Exactly one match → act on it. Several → reply `איזו מהן?` followed by one `#id title` line per match (max 8), and do nothing. None → `לא מצאתי משימה כזו`. A done/take on a task that is already completed → `#3 כבר בוצעה` (no change).

### Expense
- Amount: the first/last amount token (if both ends are amounts, the first). Date: today in Asia/Jerusalem; the word `אתמול` anywhere → yesterday, removed from the notes.
- Category, in this order: (1) an existing `categories.name` (not in `INCOME_CATEGORIES`) appearing as a whole phrase in the text, optionally with a one-letter prefix (`60 בתחבורה`) → that category, phrase removed from the notes; (2) the first keyword hit in `EXPENSE_KEYWORDS` (service constant, Hebrew keyword → category name, resolved only if that category exists in the DB — the live DB has categories the seed does not, e.g. `חתונה`, `סופר`, `דלק`); (3) `הוצאות בית` (same fallback as the card import). Initial keyword map (the implementer may extend it): דלק/תדלוק → `דלק` else `רכב`; אוטובוס/רכבת/מונית/גט → `תחבורה`; מסעדה/קפה/פיצה/המבורגר/סושי/וולט → `אוכל בחוץ`; רופא/תרופות/סופר פארם/קופת חולים → `בריאות`; סרט/קולנוע/הופעה → `פנאי`; סופר/שופרסל/רמי לוי/מכולת/ויקטורי → `סופר`; צלם/אולם/די ג'יי/דיג'יי/שמלה/חליפה/הזמנות/מגנטים/רב/טבעות/קייטרינג → `חתונה`.
- Payer = the sender's `users` row (`people.find_person`). Account = `people.default_account_id(conn, sender)`, else `כרטיס אשראי`, else the first account. Sign: `-abs(amount)` (income categories are never chosen by the bot). `tags = 'whatsapp'`, `notes` = the remaining text or NULL. Insert directly (same columns as `api_create_transaction`) and invalidate the stats cache like it does.
- Reply: `✅ נרשם: ₪350 · פרחים · הוצאות בית · מזומן` then `הוצאות החודש: ₪8,420` (`services.today.month_totals(conn, 'YYYY-MM')["expenses"]`, for the month of the expense's date) then `בטל — לביטול`. The notes segment is omitted when empty. Amounts print `₪1,200` / `₪89.90` (decimals only when non-zero).

### Task
- Title = the message minus the parts below. `due_date`: the first `עד <when>` anywhere in the sentence (so `להתקשר לצלם עד חמישי דחוף` and `עד חמישי להתקשר לצלם` both get the date and a clean title), where `<when>` is `היום` / `מחר` / `מחרתיים` / a weekday (`חמישי`, `יום חמישי`, `ה'`, `ה׳` → the **next** such day, never today) / `d.m`, `d/m`, `d.m.yy`, `d.m.yyyy` (a `d.m` with no year is the next occurrence, today or later). `עד` with anything else stays in the title and the task has no date.
- Owner: a leading `אני:` → the sender; a leading `יוסף:` / `קארינה:` (the `USER_DISPLAY_NAMES` values, `valid_owner` semantics) → that person; otherwise **unassigned** (a task written in the chat is the household's until someone says `לקחתי`).
- `דחוף` anywhere → `priority='high'`, word removed. Otherwise `medium`. `category='general'`.
- Reply: `📝 נוספה משימה #14: להתקשר לצלם · עד יום חמישי · יוסף` (the due label from `hebrew_dates.due_label`; the owner's display name; each segment omitted when absent) then `עוד 12 שבועות ו-3 ימים לחתונה` (`wedding_plan.countdown()["weeks_label"]`; omitted when there is no wedding date or it has passed) then `בטל — לביטול`.

### List
Header `📋 משימות פתוחות (7)` (or `📋 המשימות שלך (3)` for `שלי`), then one line per task ordered as the היום queue groups them (`services.today.task_group`: overdue, week, later, nodate; inside a group by due date then id): `#3 לסגור צלם · באיחור ביומיים · יוסף`. Overdue lines start with `⚠️ `. Max 20 lines, then `…ועוד 4`. Empty: `אין משימות פתוחות 🎉` / `אין משימות על שמך`. Ends with the countdown line.

### Done / Take
- Done: `completed=1`. Reply `✔️ #3 לסגור צלם — בוצע. נשארו 6 משימות פתוחות.` then `בטל — לביטול`.
- Take: `owner` = the sender's `users.name`. Reply `🙋 #3 לסגור צלם — על יוסף.` then `בטל — לביטול`. Taking a task you already own → `#3 כבר שלך`.

### Undo
Reverses the sender's last bot action, whatever it was, then forgets it (a second `בטל` → `אין מה לבטל`):
- expense → delete the transaction (only if its `tags='whatsapp'` and it still exists), invalidate stats: `↩️ ההוצאה ₪350 (פרחים) בוטלה`
- task added → delete the task: `↩️ המשימה #14 נמחקה`
- done → `completed=0`: `↩️ #3 חזרה לפתוחה`
- take → previous owner restored: `↩️ #3 חזרה ליוסף` / `↩️ #3 חזרה ללא אחראי`
Two guards, because a chat `בטל` can arrive long after the action and the other person may have touched the row in the app meanwhile:
- The remembered action expires after 24 hours (`system_settings.updated_at`): `אין מה לבטל`.
- Each reversal restates what the bot left behind in its `WHERE` (the expense still tagged `whatsapp`, the added task still open, the finished task still completed, the taken task still owned by the sender). A row the app changed since is left alone: `הפעולה האחרונה כבר השתנתה באפליקציה, לא בוטל`. A row that no longer exists gets the same reply.

### Help
```
תרשום 📒
350 פרחים — הוצאה (אפשר גם: 350 פרחים אתמול)
להתקשר לצלם עד חמישי — משימה לחתונה (אני: / יוסף: / קארינה: בהתחלה = אחראי, דחוף = עדיפות גבוהה)
משימות / שלי — מה פתוח
סיימתי 3 או סיימתי צלם — בוצע
לקחתי 3 — המשימה עליי
בטל — מבטל את הפעולה האחרונה
```

### Reliability
- The webhook returns 200 immediately; the reply is sent from a FastAPI `BackgroundTasks` call so Meta never times out. A failed send is logged, never retried.
- Each WhatsApp message id (`wamid`) is remembered in a bounded in-memory deque (256) in the service; a redelivered id is acknowledged and skipped (the app runs a single worker by design). Several messages in one webhook payload are handled in order.
- Errors inside `handle_message` are caught per message: logged with the traceback, the sender gets `משהו השתבש, נסה שוב`, and the webhook still returns 200.

## Data
No new tables or columns.
- `transactions.tags = 'whatsapp'` marks bot-created expenses (the column exists; the undo checks it before deleting).
- Undo state: `system_settings` key `whatsapp_undo:<USERNAME>` → JSON `{"kind": "expense|task|done|take", "id": 123, "prev_owner": "Yosef"|null, "label": "₪350 (פרחים)"}`; deleted on undo, overwritten by the next action, ignored once `updated_at` is older than 24 hours. Same helper style as the `push_sent:` keys.
- `hebrew_dates.today_local()` (Asia/Jerusalem, falling back to the process date) is the one "today in Israel" helper, shared with the arena push.
- Derived, never stored: month total (`today.month_totals`), countdown (`wedding_plan.countdown`), the task grouping (`today.task_group`), the payer and default account (`services/people.py`), the phone → person map (env vars, read at call time like `IMPORT_TOKEN` so tests can `monkeypatch.setenv`).

## API
New router `api/whatsapp.py`, prefix `/api/whatsapp`, included in `main.py` next to `push_api`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/whatsapp/webhook` | `@public` | Meta verification handshake. Query `hub.mode=subscribe`, `hub.verify_token`, `hub.challenge`. Token equals `WHATSAPP_VERIFY_TOKEN` (compare with `hmac.compare_digest`) → `200` plain-text body = the challenge. Otherwise `403 {"detail": "אסימון לא תקין"}`. Env var missing → `403 {"detail": "וואטסאפ כבוי"}`. |
| POST | `/api/whatsapp/webhook` | `@public` | Incoming messages. If `WHATSAPP_APP_SECRET` is unset → `403 {"detail": "וואטסאפ כבוי"}`, body unread. Verify `X-Hub-Signature-256` = `sha256=` + HMAC-SHA256(app secret, raw body) with `compare_digest` → else `401 {"detail": "חתימה לא תקינה"}`. Walk `entry[].changes[].value.messages[]`; for each: resolve `from` (wa_id) to a household username via the phone env vars; unknown → skip; `type != "text"` → reply the text-only line; else dedup by `id`, call `handle_message`, queue `send_text(to=wa_id, text=reply, reply_to=message id)` as a background task. Status/receipt payloads (no `messages`) → ignore. Always `200 {"handled": n}` once the signature passes. |
| POST | `/api/whatsapp/test` | session (household only — module-only users are already blocked by `can_access_path`) | Body `{"text": "350 פרחים"}` → `{"reply": "..."}`. Runs `handle_message` with the session user as the sender and **does not send anything**. Lets Yosef try the grammar from the browser before Meta is wired, and keeps the tests independent of the provider. |

`services/whatsapp.py` exposes:
- `config() -> dict | None` (`access_token`, `phone_number_id`, `api_version` default `v22.0`), `is_enabled()`.
- `sender_for(wa_id) -> str | None` (username), from `WHATSAPP_PHONE_YOSEF` / `WHATSAPP_PHONE_KARINA`, digits-only comparison.
- `handle_message(conn, user, text, today: date | None = None) -> str` — the whole grammar; pure given the connection; `today` injectable for tests.
- `send_text(to, text, reply_to=None) -> bool` — `httpx.post` to `https://graph.facebook.com/{api_version}/{phone_number_id}/messages` with `{"messaging_product":"whatsapp","to":to,"type":"text","text":{"body":text},"context":{"message_id":reply_to}}` (context only when given), bearer `WHATSAPP_ACCESS_TOKEN`, 10 s timeout; logs and returns False on any failure. Tests monkeypatch this.
- `verify_signature(secret, body: bytes, header: str | None) -> bool`.

### Provider setup (outside the code, for Yosef)
1. Meta for Developers → create an app (type Business) → add the WhatsApp product. The free **test number** it gives can message up to 5 verified recipients: add Yosef's and Karina's phones. Free-form replies are allowed for 24 h after each incoming message, which is always the case here.
2. Railway variables: `WHATSAPP_VERIFY_TOKEN` (any random string), `WHATSAPP_APP_SECRET` (app dashboard → Settings → Basic), `WHATSAPP_ACCESS_TOKEN` (a permanent System User token with `whatsapp_business_messaging`), `WHATSAPP_PHONE_NUMBER_ID` (WhatsApp → API setup), `WHATSAPP_PHONE_YOSEF`, `WHATSAPP_PHONE_KARINA`.
3. WhatsApp → Configuration → Webhook: callback `https://expensetracker-production-2084.up.railway.app/api/whatsapp/webhook`, the verify token above, subscribe to the `messages` field.
4. Send `עזרה` from either phone.

## Files to touch
- `app/backend/app/services/whatsapp.py` — **new**: config, phone map, grammar (`handle_message`), undo state, dedup deque, `send_text`, signature check. Reuses `people`, `today.month_totals`, `today.task_group`, `hebrew_dates`, `wedding_plan.countdown`, `cache_service`.
- `app/backend/app/api/whatsapp.py` — **new**: the three routes above.
- `app/backend/app/schemas/whatsapp.py` — **new**: `TestMessage(text: str)`.
- `app/backend/app/main.py` — import + `app.include_router(whatsapp_api)`.
- `.env.example` — the six `WHATSAPP_*` variables with one-line comments.
- `CLAUDE.md` — env var table (six rows), API routes table (`whatsapp_api`), Services list (`whatsapp` — תרשום), project structure tree (two new files).
- `tests/test_whatsapp_e2e.py` — **new**.
- No frontend files. No new dependencies (`httpx` is already pinned).

## Acceptance criteria
1. `GET /api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=<right>&hub.challenge=abc` returns 200 with body `abc` and no auth; a wrong token returns 403; without `WHATSAPP_VERIFY_TOKEN` it returns 403 `וואטסאפ כבוי`.
2. `POST /api/whatsapp/webhook` without a valid `X-Hub-Signature-256` returns 401 and changes nothing; with `WHATSAPP_APP_SECRET` unset returns 403.
3. A correctly signed text message from an unknown wa_id returns 200 `{"handled": 0}`, inserts nothing and sends nothing.
4. `350 פרחים` from Karina's phone inserts one transaction: amount −350, user = Karina, account = כרטיס אשראי, category הוצאות בית, notes `פרחים`, tags `whatsapp`, date = today; the reply starts with `✅ נרשם: ₪350 · פרחים · הוצאות בית · כרטיס אשראי` and contains `הוצאות החודש: ₪`. The same text from Yosef's phone lands on מזומן.
5. `פיצה 89.90 אתמול` → category אוכל בחוץ, date = yesterday, notes `פיצה`. `120 רכב` → category רכב (whole-name match), notes NULL.
6. `להתקשר לצלם עד חמישי` adds an open wedding task titled `להתקשר לצלם`, owner NULL, priority medium, `due_date` = the next Thursday after today; the reply contains `📝 נוספה משימה #` and `עוד` + `לחתונה` when a wedding date is set. `קארינה: דחוף לאשר תפריט עד 3.11` → owner Karina, priority high, title `לאשר תפריט`, due 3 Nov of the next occurrence.
7. `משימות` lists only open tasks, overdue ones first and marked `⚠️`, capped at 20 lines with `…ועוד n`; `שלי` lists only the sender's. With no open tasks: `אין משימות פתוחות 🎉`.
8. `סיימתי 3` marks task 3 completed and replies `✔️ #3 … — בוצע. נשארו n משימות פתוחות.`; `סיימתי צלם` with two open matches replies `איזו מהן?` with both and changes nothing; with no match replies `לא מצאתי משימה כזו`; on a completed task replies `#3 כבר בוצעה`.
9. `לקחתי 3` sets owner to the sender; the reply names the sender in Hebrew.
10. `בטל` after each of expense / task / done / take reverses exactly that action with the matching `↩️` reply; a second `בטל` replies `אין מה לבטל`. Undo never deletes a transaction whose `tags` is not `whatsapp`.
11. The same `wamid` delivered twice inserts once; the second delivery still returns 200.
12. A single unknown word (`בוקר`) replies with `לא הבנתי.` followed by the help text, and inserts nothing. A two-word unknown message becomes a task.
13. `POST /api/whatsapp/test` returns the reply without calling `send_text`; Yonatan (workouts-only session) gets 403 from the middleware.
14. `ruff check .` and the full `python -m pytest` pass; no desktop or mobile page changes (no file under `app/frontend/` touched).

## Tests to add
`tests/test_whatsapp_e2e.py` — helpers: `_signed(client, payload, secret)` builds a Meta-shaped body (`entry[0].changes[0].value.messages[0]` with `from`, `id`, `type`, `text.body`) and the `sha256=` header; a `sent` list fixture that monkeypatches `whatsapp.send_text` to append `(to, text, reply_to)`; `monkeypatch.setenv` for the six variables; wedding date set via `wedding_settings` for the countdown assertions; grammar cases call `whatsapp.handle_message(db_conn, "KARINA", text, today=date(2032, 3, 10))` directly for deterministic dates (a Wednesday).
- `test_webhook_verify_handshake` — AC 1.
- `test_webhook_rejects_bad_signature_and_when_off` — AC 2.
- `test_unknown_sender_is_ignored` — AC 3.
- `test_expense_from_each_phone_uses_their_account` — AC 4 (asserts the inserted row and the reply text; `sent[0].reply_to` equals the wamid).
- `test_expense_category_and_yesterday` — AC 5.
- `test_task_with_weekday_owner_priority_and_date` — AC 6.
- `test_list_groups_caps_and_mine` — AC 7.
- `test_done_by_id_fragment_ambiguous_missing_and_already_done` — AC 8.
- `test_take_sets_owner` — AC 9.
- `test_undo_each_kind_and_nothing_to_undo` — AC 10.
- `test_duplicate_wamid_handled_once` — AC 11.
- `test_unknown_single_word_gets_help` — AC 12.
- `test_test_endpoint_returns_reply_without_sending` and `test_whatsapp_api_blocked_for_workouts_only_user` — AC 13 (the access test follows `tests/test_workouts_access_e2e.py`).
- `test_whatsapp_webhook_is_public_but_test_is_not` — `build_public_route_matchers` includes GET+POST `/api/whatsapp/webhook` and not `/api/whatsapp/test` (pattern from `test_card_import_e2e.py`).

## Out of scope
- Any UI in the app (no settings page, no chat log screen, no link on `/more`).
- Interactive buttons / list messages, media (receipt photos, voice), reactions.
- Editing an expense's category or amount by chat (fix in the app, or `בטל` and retype with the category name).
- Renovation tasks, workouts, Yonatan and Tsahala (the bot knows two phones only).
- Outbound notifications from the app (morning digest, task reminders) — a natural phase 2 on the same `send_text`, but Meta requires approved templates outside the 24-hour window.
- LLM parsing of free text.
- Twilio or a whatsapp-web.js bridge (Node) — the latter breaks the no-build-step rule and is against WhatsApp's terms.

## Open questions
1. **Provider:** the spec assumes the Meta WhatsApp Cloud API (official, free at this volume, no new dependency, test number works immediately). Say so if you would rather use Twilio's WhatsApp sandbox — only `send_text`, the signature check and the webhook payload shape change.
2. **Phone numbers:** the implementer needs no numbers (they are env vars), but you will need both phones' numbers in international digits for Railway.
