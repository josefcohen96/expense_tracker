---
name: api-endpoint
description: Add a new JSON REST API endpoint to the expense tracker following the project's existing patterns. Use when creating new GET, POST, PATCH, or DELETE routes in the api/ directory.
metadata:
  author: kiro
  version: 1.0.0
---

## Context

All JSON API routes live in `app/backend/app/api/`. The project uses:
- **FastAPI** with `APIRouter`
- **Raw `sqlite3`** — no ORM, no query builder
- **`sqlite3.Row`** factory — access columns by name (`row["column"]`) or `dict(row)`
- **Pydantic v2** for request/response schemas in `app/backend/app/schemas/`
- **`Depends(get_db_conn)`** for DB injection — the connection is opened and closed per request
- **`cache_service`** for invalidating the statistics cache on writes

Registered routers in `app/backend/app/main.py`:
- `transactions_api` → `/api/transactions`
- `recurrences_api` → `/api/recurrences`
- `system_api` → `/api/system`
- `statistics_api` → `/api/statistics`
- `backup_api` → `/api/backup`
- `wedding_api` → `/api/wedding`

## Workflow

### Step 1: Read before writing
Read the most similar existing endpoint file (e.g., `app/backend/app/api/transactions.py` for a CRUD endpoint). Match its style exactly.

### Step 2: Schema first
If the endpoint accepts or returns a body, define Pydantic models in `app/backend/app/schemas/` before writing the endpoint. Follow the Base/Create/Update/Response pattern:

```python
class ThingBase(BaseModel):
    name: str
    amount: float
    optional_field: Optional[str] = None

class ThingCreate(ThingBase):
    pass

class ThingUpdate(BaseModel):
    # All fields Optional for PATCH
    name: Optional[str] = None
    amount: Optional[float] = None

class Thing(ThingBase):
    id: int
```

### Step 3: Write the endpoint

Use this canonical pattern:

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from ..db import get_db_conn
from .. import schemas
import sqlite3

router = APIRouter(prefix="/api/things", tags=["things"])

@router.get("", response_model=List[schemas.Thing])
async def api_get_things(
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> List[schemas.Thing]:
    rows = db_conn.execute("SELECT * FROM things ORDER BY id DESC").fetchall()
    return [schemas.Thing(**dict(row)) for row in rows]

@router.post("", response_model=schemas.Thing)
async def api_create_thing(
    body: schemas.ThingCreate,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> schemas.Thing:
    cur = db_conn.execute(
        "INSERT INTO things (name, amount) VALUES (?, ?)",
        (body.name, body.amount),
    )
    db_conn.commit()
    row = db_conn.execute("SELECT * FROM things WHERE id = ?", (cur.lastrowid,)).fetchone()
    return schemas.Thing(**dict(row))

@router.patch("/{thing_id}", response_model=schemas.Thing)
async def api_update_thing(
    thing_id: int,
    update: schemas.ThingUpdate,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> schemas.Thing:
    fields = update.dict(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join([f"{k} = ?" for k in fields.keys()])
    params = list(fields.values()) + [thing_id]
    db_conn.execute(f"UPDATE things SET {set_clause} WHERE id = ?", params)
    db_conn.commit()
    row = db_conn.execute("SELECT * FROM things WHERE id = ?", (thing_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Thing not found")
    return schemas.Thing(**dict(row))

@router.delete("/{thing_id}")
async def api_delete_thing(
    thing_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> JSONResponse:
    db_conn.execute("DELETE FROM things WHERE id = ?", (thing_id,))
    db_conn.commit()
    return JSONResponse(content={"deleted": True})
```

### Step 4: Register the router

In `app/backend/app/main.py`, import the router and call `app.include_router(...)`. Place it near the other API routers.

### Step 5: Cache invalidation

If the endpoint writes data that affects statistics (transactions, categories), call:
```python
from ..services.cache_service import cache_service
cache_service.invalidate("top_expenses_3months")
```

## Checklist before finishing

- [ ] Schema defined in `app/backend/app/schemas/` (or added to an existing schema file)
- [ ] Router uses `APIRouter(prefix="/api/...", tags=[...])`
- [ ] All DB access uses parameterized queries — never f-string SQL with user input
- [ ] PATCH endpoints use `update.dict(exclude_unset=True)` to allow partial updates
- [ ] 404 is raised when a row is not found on GET/{id}, PATCH, DELETE
- [ ] `db_conn.commit()` is called after every write
- [ ] Router is imported and registered in `main.py`
- [ ] Verify with: `curl http://localhost:8000/api/your-endpoint`

## Key rules

- **Never use f-strings for SQL with user-provided values** — always use `?` placeholders
- **`dict(row)`** converts a `sqlite3.Row` to a plain dict — required before Pydantic construction
- **`exclude_unset=True`** on PATCH is critical — without it, optional fields default to `None` and wipe existing data
- **Amount sign convention**: expenses are negative (`-abs(amount)`), income is positive
- **Income categories** (Hebrew): `משכורת`, `קליניקה` — amounts for these should stay positive
