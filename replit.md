# Expense Tracker

A full-stack personal finance tracking application built with FastAPI (Python) and SQLite.

## Architecture

- **Backend**: FastAPI + Uvicorn, running on port 5000
- **Database**: SQLite at `app/backend/data/budget.db`
- **Templates**: Jinja2 (server-side rendered HTML)
- **Scheduler**: APScheduler for recurring expense automation
- **Auth**: Session-based authentication with middleware

## Project Structure

```
app/
  backend/
    app/
      api/          # REST API endpoints (transactions, recurrences, backup, statistics)
      routes/       # Page and partial routes (Jinja2 HTML responses)
      services/     # Auth middleware, cron, logging, cache, backup services
      schemas/      # Pydantic schemas
      main.py       # FastAPI app entry point
      db.py         # SQLite connection and DB initialization
      auth.py       # Auth helpers
      recurrence.py # Recurring expense logic
    data/           # SQLite database file
  frontend/
    static/         # CSS, JS, static assets
    templates/      # Jinja2 HTML templates
tests/              # E2E test suite
```

## Running the App

```bash
uvicorn app.backend.app.main:app --host 0.0.0.0 --port 5000 --reload
```

## Key Features

- Expense/income tracking with categories, users, accounts
- Monthly budget tracking with visual dashboard
- Recurring expenses with automated scheduling (APScheduler)
- Data export/import via Excel
- Backup and restore functionality
- Authentication with session cookies

## Environment Variables

- `SESSION_SECRET_KEY` - Secret for session signing (has a default)
- `BUDGET_DB_PATH` - Override SQLite DB path (default: `app/backend/data/budget.db`)
- `AUTH_ENABLED` - Set to `0` to disable auth (only works under pytest)
- `COOKIE_SAMESITE` - Cookie SameSite policy (default: `lax`)
- `FORCE_DB_RESET` - Set to `1` to reset the database on startup

## Dependencies

See `requirements.txt`. Key packages: fastapi, uvicorn, jinja2, apscheduler, openpyxl, httpx, pydantic, python-dateutil, itsdangerous.
