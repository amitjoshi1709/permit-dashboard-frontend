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

No test suite exists yet — all testing is manual.

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
- `celery_app.py` — Celery configuration. Redis as broker+backend. Prefetch multiplier=1 (one task at a time since Playwright is resource-heavy). Timezone: America/New_York.
- `tasks.py` — Celery task definition + `SCRIPT_REGISTRY` mapping `(state_code, permit_type)` tuples to runner functions. Uses `None` as wildcard permit type for states that use one runner for all types. Redis stores job status (expires 1hr).
- `database.py` — Supabase client. `COLUMN_MAP` translates between Supabase's space-separated column names (e.g., `"First Name"`) and camelCase JSON keys. All driver queries hit the `fleet` table; permits hit the `permits` table.
- `models.py` — Pydantic request/response models.
- `config.py` — Company constants (address, USDOT, insurance), supported states set, valid permit types set.
- `scripts/<state>/runner.py` — Playwright automation per state. Each exposes `run(permit, job_id, on_captcha_needed, company)`. Currently implemented: Alabama (TAP + OSOW), Georgia, Arkansas.

### API Endpoints
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/drivers` | Fetch all active drivers |
| POST | `/api/drivers` | Create driver |
| PUT | `/api/drivers/{driver_id}` | Update driver |
| DELETE | `/api/drivers/{driver_id}` | Soft delete (sets active=False) |
| POST | `/api/permits/order` | Queue batch permit automation job |
| GET | `/api/permits/status/{job_id}` | Poll job status from Redis |
| POST | `/api/orders/{job_id}/captcha-solved` | Signal CAPTCHA completion |
| GET | `/api/permits/history` | Fetch permit history |
| GET | `/api/permits/blankets` | Stub — returns empty array |

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

## State Scripts

**Supported states** (config.py): GA, FL, SC, NC, TN, AL, MS, LA, TX, AR

**Implemented scripts** (4 of 10):

| State | Script | Permit Types | Notes |
|-------|--------|-------------|-------|
| AL | `alabama_tf/runner.py` | trip, fuel, trip_fuel | CapSolver CAPTCHA integration; 3-page form |
| AL | `alabama_osow/runner.py` | os_ow | Login required (AL_USERNAME/AL_PASSWORD) |
| GA | `georgia_tf/runner.py` | trip, fuel, trip_fuel | Login required (GA_PORTAL_USERNAME/GA_PORTAL_PASSWORD); twin forms for trip_fuel; has `transforms.py` |
| AR | `arkansas_trip/runner.py` | trip | No login; 7-step form |

All scripts: `chromium.launch(headless=False)` with `--disable-blink-features=AutomationControlled`.

### Script Registry (tasks.py)
```python
SCRIPT_REGISTRY = {
    ("AL", "trip_fuel"): run_alabama_tf,
    ("AL", "trip"):      run_alabama_tf,
    ("AL", "fuel"):      run_alabama_tf,
    ("AL", "os_ow"):     run_alabama_osow,
    ("GA", None):        run_georgia_tf,   # None = wildcard, handles all permit types
    ("AR", None):        run_arkansas_trip,
}
```

## Data Ownership

The dashboard sends **only** driver IDs, state codes, permit type, and effective date. All permit form data (VIN, USDOT, insurance, carrier details) is resolved server-side from Supabase. The frontend never holds or sends this data.

## Adding a New State

1. Create `backend/scripts/<state>/runner.py` with `run(permit, job_id, on_captcha_needed, company)` function
2. Import and register in `tasks.py` `SCRIPT_REGISTRY` — use `(state, None)` tuple if one runner handles all permit types, or explicit `(state, type)` entries
3. Add state code to `SUPPORTED_STATES` in `config.py`
4. Add state to `STATES` array in `src/api.js`
5. Add any portal credentials to `.env`
6. Restart Celery worker

## Environment Variables (backend/.env)

Required: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `REDIS_URL`

Per-state portal credentials: `GA_PORTAL_USERNAME`, `GA_PORTAL_PASSWORD`, `GA_ACCOUNT_NO`, `AL_USERNAME`, `AL_PASSWORD`

Optional: `CAPSOLVER_API_KEY` (Alabama TAP CAPTCHA), `CAPTCHA_MODE` (terminal|dashboard)

## Key Conventions

- Backend `.env` has Supabase credentials and portal logins — never commit it (`.env.example` exists)
- Frontend `API_BASE` in `src/api.js` points to `http://127.0.0.1:8000` — change only for production
- Supabase `fleet` table uses human-readable column names with spaces (e.g., `"Tractor Number"`); `database.py` COLUMN_MAP handles translation
- Company driver types (`F`, `LP`, `T`) use shared insurance/USDOT from `config.py`; owner-operators must have their own insurance fields in Supabase
- FastAPI CORS is configured for `http://localhost:5173` in `app.py`
- Tailwind theme: dark industrial with custom palette — navy (#0D1B2A), gold accent (#f0a500). Fonts: DM Sans (body), DM Mono (monospace). See `tailwind.config.js` for full color tokens.
- Vite proxy in `vite.config.js` routes `/api` to `:3001` but is unused — `src/api.js` hardcodes `API_BASE` to `:8000` directly
- Drivers are soft-deleted (active=False), never removed from Supabase
- Permit IDs are sequential (P0001–P9999+), pre-generated to avoid duplicates
