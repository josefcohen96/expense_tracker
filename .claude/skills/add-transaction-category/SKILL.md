---
name: add-transaction-category
description: Add a new spending or income category to the expense tracker. Use when the user wants a new category to appear in the transaction form, statistics, and filters.
metadata:
  author: kiro
  version: 1.0.0
---

## Context

Categories are stored in the `categories` table (`id, name, is_saving`). They are seeded once in `initialise_database()` in `app/backend/app/db.py`. Category names are in **Hebrew**. The `is_saving` flag marks savings categories (like חסכונות) which are excluded from expense statistics.

**Income categories** are identified by name in SQL queries — not by a DB flag. The two income categories are: `משכורת` and `קליניקה`. They are hardcoded in multiple SQL queries via `c.name NOT IN ('משכורת', 'קליניקה')`.

Adding a new income category is a bigger change than adding an expense category — see the Income Category section below.

## Workflow: Adding an expense or savings category

### 1. Add to the seed data in `db.py`

In `app/backend/app/db.py`, find the seed block:
```python
if not cur.execute("SELECT COUNT(*) FROM categories").fetchone()[0]:
    for _cat, _is_saving in [
        ("משכורת", 0), ...
    ]:
        cur.execute("INSERT INTO categories (name, is_saving) VALUES (?, ?)", (_cat, _is_saving))
```

Add your new category to this list. Set `is_saving=1` for savings categories, `0` for regular expenses.

**Note:** The seed block only runs on a **fresh database**. For an existing database, also add a runtime insert:

```python
# After the migrations section in initialise_database():
try:
    exists = cur.execute("SELECT 1 FROM categories WHERE name = ?", ("שם הקטגוריה",)).fetchone()
    if not exists:
        cur.execute("INSERT INTO categories (name, is_saving) VALUES (?, ?)", ("שם הקטגוריה", 0))
except Exception:
    pass
```

### 2. Verify statistics exclusions in `app/backend/app/api/statistics.py`

Check whether the new category should appear in expense statistics. The statistics API excludes:
- Income categories: `c.name NOT IN ('משכורת', 'קליניקה')`
- Savings categories: `COALESCE(c.is_saving, 0) = 0`

If the new category is a savings category, set `is_saving=1` — it will automatically be excluded from expense stats and included in the savings total query.

If the new category is a regular expense category, no changes are needed in `statistics.py` — it will automatically appear.

### 3. Check the frontend category filter

Look in `app/frontend/templates/finances/` for any hardcoded category lists in HTML templates. If categories are loaded dynamically from the API, no change is needed. If there are hardcoded `<option>` or `<select>` elements, add the new category there too.

### 4. Check `_is_income_category` in `app/backend/app/api/transactions.py`

```python
def _is_income_category(db_conn, category_id):
    row = db_conn.execute("SELECT name FROM categories WHERE id = ?", (category_id,)).fetchone()
    return row[0] in ("משכורת", "קליניקה")
```

If the new category is **income**, add its Hebrew name to this tuple. This controls whether transaction amounts are stored as positive (income) or negative (expense).

## Workflow: Adding an income category

Income categories require changes in more places because they are identified by name in hardcoded SQL strings. For each of the queries below, add the new Hebrew name to the exclusion list:

**Files to update:**
1. `app/backend/app/api/transactions.py` → `_is_income_category()` function — add name to the tuple
2. `app/backend/app/api/statistics.py` → every query with `c.name NOT IN ('משכורת', 'קליניקה')` — add the new name
3. `app/backend/app/db.py` → seed data block — add with `is_saving=0`
4. Grep for the Hebrew income category names to catch any other occurrences:
   ```
   Select-String -Path app\backend\**\*.py -Pattern "משכורת"
   ```

## Checklist

- [ ] Category added to seed block in `db.py`
- [ ] Runtime insert added to `initialise_database()` for existing databases
- [ ] `is_saving` flag is correct (`0` for expense, `1` for savings)
- [ ] If income category: `_is_income_category()` in `transactions.py` updated
- [ ] If income category: all `NOT IN ('משכורת', 'קליניקה')` SQL strings updated
- [ ] Frontend category dropdowns verified (dynamic load = no change needed)
- [ ] Statistics cache cleared after testing: `POST /api/statistics/clear-cache`

## Common pitfalls

- The seed block is guarded by `if not count` — it won't re-run on existing databases. Always add a runtime insert too.
- Savings categories (`is_saving=1`) are excluded from expense totals — double-check which queries use `COALESCE(c.is_saving, 0) = 0`
- The `_is_income_category()` function controls amount sign at write time — getting this wrong will store income as negative
