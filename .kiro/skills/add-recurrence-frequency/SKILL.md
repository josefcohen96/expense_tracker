---
name: add-recurrence-frequency
description: Add a new recurrence frequency type (e.g. bi-weekly, quarterly) to the recurring transactions engine. Use when a new charge interval is needed beyond the existing monthly/weekly/yearly options.
metadata:
  author: kiro
  version: 1.0.0
---

## Context

The recurring transaction engine uses a **catch-up materialization** model. When the app starts (or a cron job fires), it calls `apply_recurring()` in `app/backend/app/recurrence.py`, which loops over all active recurrences and inserts any past-due transactions. The `next_charge_date` column drives when the next transaction fires.

Supported frequencies today: `monthly`, `weekly`, `yearly`.

The frequency string is stored in the `recurrences.frequency` column and must be handled in three places:
1. **`recurrence.py`** — the engine that advances `next_charge_date`
2. **`api/recurrences.py`** — sets the initial `next_charge_date` on create/update
3. **`schemas/recurrences.py`** — Pydantic validation (currently a plain `str`, consider adding a validator)

## Workflow

### Step 1: Add the advance logic in `recurrence.py`

Open `app/backend/app/recurrence.py` and find `_compute_next_charge_date()`:

```python
def _compute_next_charge_date(current_due, freq, day_of_month, weekday):
    if freq == "monthly":
        return _add_months_keep_dom(current_due, 1, day_of_month)
    if freq == "weekly":
        return current_due + timedelta(days=7)
    if freq == "yearly":
        ...
    return current_due + timedelta(days=1)  # fallback
```

Add a new `if freq == "your-frequency":` branch **before** the fallback return. Examples:
- Bi-weekly: `return current_due + timedelta(days=14)`
- Quarterly: `return _add_months_keep_dom(current_due, 3, day_of_month)`
- Every 2 years: `return current_due.replace(year=current_due.year + 2)`

### Step 2: Add `next_charge_date` calculation for create in `api/recurrences.py`

In `api_create_recurrence()`, there is an `if not next_charge_date:` block that sets the initial value per frequency. Add a matching branch for the new frequency:

```python
elif frequency == "biweekly":
    next_charge_date = (date.today() + timedelta(days=14)).isoformat()
```

Do the same in `api_update_recurrence()` inside the `if "frequency" in fields and "next_charge_date" not in fields:` block.

### Step 3: Update the `db.py` migration (if schema changes)

If the new frequency requires a new column (e.g., a `day_of_quarter` field), add it using the inline migration pattern in `db.py`. See the `db-migration` skill for details.

If the new frequency uses only existing columns (`day_of_month`, `weekday`, `next_charge_date`), no DB change is needed.

### Step 4: Update the Pydantic schema (optional but recommended)

In `app/backend/app/schemas/recurrences.py`, the `frequency` field is a plain `str`. Consider adding a validator:

```python
from pydantic import field_validator

class RecurrenceBase(BaseModel):
    frequency: str

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v):
        allowed = {"monthly", "weekly", "yearly", "biweekly"}
        if v not in allowed:
            raise ValueError(f"frequency must be one of {allowed}")
        return v
```

### Step 5: Update the frontend

Look for frequency `<select>` dropdowns in `app/frontend/templates/`. Add a new `<option value="biweekly">כל שבועיים</option>` (Hebrew label).

## Checklist

- [ ] `_compute_next_charge_date()` in `recurrence.py` handles the new frequency
- [ ] Initial `next_charge_date` logic added in `api_create_recurrence()` for the new frequency
- [ ] Initial `next_charge_date` logic added in `api_update_recurrence()` for the new frequency
- [ ] DB migration added if new columns are needed
- [ ] Pydantic schema validator updated to include the new frequency string
- [ ] Frontend `<select>` dropdown updated with the new option (Hebrew label)
- [ ] Test by creating a recurrence with the new frequency and calling `POST /api/system/apply-recurring`

## Common pitfalls

- The fallback `return current_due + timedelta(days=1)` at the end of `_compute_next_charge_date()` will silently fire every day for unknown frequencies. Always add an explicit branch.
- `apply_recurring()` loops `while next_charge_date <= today` — a bad advance calculation that returns a date in the past will cause an infinite loop. Always verify the new date is strictly after `current_due`.
- Both `api_create_recurrence()` and `api_update_recurrence()` have their own `if not next_charge_date` / `if "frequency" in fields` blocks — you must update **both**.
