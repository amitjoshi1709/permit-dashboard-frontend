# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Dispatcher-facing permit ordering dashboard for Mega Trucking LLC. Dispatchers select drivers and states, the backend resolves all permit form data from Supabase, queues Playwright automation jobs via Celery/Redis, and fills state DMV portal forms — stopping before payment.

## Commands

### Frontend (root directory)
```bash
npm run dev          # Vite dev server on :5173
npm run build        # Production build to dist/
npm run lint         # ESLint
npm run preview      # Preview production build
```

### Backend (from `backend/` directory)
```bash
# One-time setup
pip install -r requirements.txt
playwright install chromium

# Three processes must run simultaneously:
docker run -d -p 6379:6379 --name redis redis:alpine   # Redis broker
uvicorn app:app --reload --port 8000                    # FastAPI on :8000
celery -A celery_app worker --loglevel=info --pool=solo # Celery (--pool=solo required on Windows)
```

## Architecture

**Two-process full-stack app:**

```
React+Vite (:5173) → FastAPI (:8000) → Celery → Redis (:6379)
                          ↕                  ↓
                      Supabase          Playwright (state DMV portals)
```

### Frontend (React + Vite + Tailwind)
- `src/api.js` — all HTTP calls to the backend; `API_BASE` constant controls the target. Also exports constants: `STATES`, `PERMIT_TYPES`, `DRIVER_TYPES`, `COMPANY_TYPES`, `COMPANY_DEFAULTS`.
- `src/App.jsx` — view router via `activeView` state. Sidebar-driven navigation between: dashboard, order, history, blankets, drivers, settings.
- No routing library — views switch via `useState("dashboard")`.
- No state management library — `useState`/`useCallback` only.

### Backend (FastAPI + Celery + Supabase)
- `app.py` — FastAPI endpoints (drivers CRUD, permit ordering, job status polling, CAPTCHA signal).
- `tasks.py` — Celery task definition + `SCRIPT_REGISTRY` mapping state codes to runner functions. Redis stores job status (expires 1hr).
- `database.py` — Supabase client. `COLUMN_MAP` translates between Supabase's space-separated column names (e.g., `"First Name"`) and camelCase JSON keys. All driver queries hit the `fleet` table; permits hit the `permits` table.
- `models.py` — Pydantic request/response models.
- `config.py` — Company constants (address, USDOT, insurance), supported states set, valid permit types set.
- `scripts/<state>/runner.py` — Playwright automation per state. Each exposes `run(permit, job_id, on_captcha_needed, company)`. Currently implemented: Alabama, Georgia.

### Data Flow (permit ordering)
1. Frontend sends `POST /api/permits/order` with `{driverIds, states, permitType, effectiveDate}`
2. FastAPI looks up full driver records from Supabase, builds permit objects with insurance/USDOT (company defaults for F/LP/T types, driver's own for owner-operators)
3. Inserts permit rows into Supabase as "Pending", fires Celery task, returns `jobId`
4. Frontend polls `GET /api/permits/status/{jobId}` every 3 seconds
5. Celery worker dispatches to the state-specific runner via `SCRIPT_REGISTRY`
6. If CAPTCHA appears: job pauses (`waiting_captcha`), user solves in browser, signals via `POST /api/orders/{jobId}/captcha-solved`

### CAPTCHA Modes
- `CAPTCHA_MODE=terminal` — Celery terminal blocks on `input()` (local dev)
- `CAPTCHA_MODE=dashboard` — polls Redis for signal from the frontend (production)

## Data Ownership

The dashboard sends **only** driver IDs, state codes, permit type, and effective date. All permit form data (VIN, USDOT, insurance, carrier details) is resolved server-side from Supabase. The frontend never holds or sends this data.

## Adding a New State

1. Create `backend/scripts/<state>/runner.py` with a `run()` function
2. Import and register in `tasks.py` `SCRIPT_REGISTRY`
3. Add state code to `SUPPORTED_STATES` in `config.py`
4. Add state to `STATES` array in `src/api.js`
5. Restart Celery worker

## Key Conventions

- Backend `.env` has Supabase credentials and `REDIS_URL` — never commit it (`.env.example` exists)
- Frontend `API_BASE` in `src/api.js` points to `http://127.0.0.1:8000` — change only for production
- Supabase `fleet` table uses human-readable column names with spaces (e.g., `"Tractor Number"`); `database.py` COLUMN_MAP handles translation
- Company driver types (`F`, `LP`, `T`) use shared insurance/USDOT from `config.py`; owner-operators must have their own insurance fields in Supabase
- FastAPI CORS is configured for `http://localhost:5173` in `app.py`
- Theme: dark industrial (#0f1117 background, #f0a500 amber accent)
