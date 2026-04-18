# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Dispatcher-facing permit ordering dashboard for Mega Trucking LLC. Dispatchers select drivers and states, the backend resolves all permit form data from Supabase, queues Playwright automation jobs via Celery/Redis, and fills state DMV portal forms — including payment where supported (Mississippi). Other states stop before payment.

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

# Four processes must run simultaneously:
docker start redis                                       # Redis broker (or: docker run -d -p 6379:6379 --name redis redis:alpine)
uvicorn app:app --reload --port 8000                     # FastAPI on :8000
celery -A celery_app worker --loglevel=info --pool=solo  # Celery (--pool=solo required on Windows)
npm run dev                                              # Vite dev server (from root directory)
```

No test suite exists yet — all testing is manual.

## Architecture

**Full-stack app (4 processes):**

```
React+Vite (:5173) → FastAPI (:8000) → Celery → Redis (:6379)
                          ↕                  ↓
                      Supabase          Playwright (state DMV portals)
```

### Frontend (React + Vite + Tailwind)
- `src/api.js` — all HTTP calls to the backend; `API_BASE` constant controls the target. Also exports constants: `STATES`, `PERMIT_TYPES`, `DRIVER_TYPES`, `COMPANY_TYPES`, `COMPANY_DEFAULTS`.
- `src/App.jsx` — view router via `activeView` state. Sidebar-driven navigation between: dashboard, order, history, blankets, drivers, settings.
- `src/components/OrderForm.jsx` — cart-based permit ordering with queue, job tracker, insurance fields (GA-only), and FL defaults from `fl_permit_defaults.json`.
- `src/components/HistoryTable.jsx` — permit history with smart filters (common combos, status pills, driver search) and duplicate-to-cart feature.
- `src/components/DriversView.jsx` — driver database with search, CRUD, and Mega insurance bulk-update.
- `src/components/SettingsView.jsx` — payment card management (encrypted server-side) and receipt delivery settings.
- `src/components/JobTracker.jsx` — real-time order progress with status sorting (running → queued → error → success).
- `src/components/Login.jsx` — JWT-based login screen.
- No routing library — views switch via `useState("dashboard")`.
- No state management library — `useState`/`useCallback` only.

### Backend (FastAPI + Celery + Supabase)
- `app.py` — FastAPI endpoints (drivers CRUD, permit ordering, job status polling, CAPTCHA signal, payment card, mega insurance).
- `celery_app.py` — Celery configuration. Redis as broker+backend. Prefetch multiplier=1 (one task at a time since Playwright is resource-heavy). Timezone: America/New_York.
- `tasks.py` — Celery task definition + `SCRIPT_REGISTRY` mapping `(state_code, permit_type)` tuples to runner functions. Uses `None` as wildcard permit type for states that use one runner for all types. Redis stores job status (expires 1hr). Fetches decrypted payment card from Supabase and passes to runners.
- `database.py` — Supabase client. `COLUMN_MAP` translates between Supabase's space-separated column names (e.g., `"First Name"`) and camelCase JSON keys. Tables: `fleet` (drivers), `permits` (history), `settings` (encrypted config).
- `encryption.py` — Fernet symmetric encryption for payment card data. Key from `CARD_ENCRYPTION_KEY` env var.
- `models.py` — Pydantic request/response models.
- `config.py` — Company constants (address, USDOT, insurance), supported states set, valid permit types set.
- `auth.py` — JWT authentication. Single shared credential from env vars. 7-day token TTL.
- `form_fields.py` — Backend-driven form field schemas for state-specific permit requirements (GA OS/OW dimensions, FL dimensions/axles/load info).
- `scripts/<state>/runner.py` — Playwright automation per state. Each exposes `run(permit, job_id, on_captcha_needed, company, payment_card)`.

### API Endpoints
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/auth/login` | Authenticate, returns JWT token |
| GET | `/api/auth/me` | Verify current token |
| GET | `/api/drivers` | Fetch all active drivers |
| POST | `/api/drivers` | Create driver |
| PUT | `/api/drivers/{driver_id}` | Update driver |
| DELETE | `/api/drivers/{driver_id}` | Soft delete (sets active=False) |
| GET | `/api/drivers/mega-insurance` | Fetch shared Mega insurance |
| PUT | `/api/drivers/mega-insurance` | Update all F/LP/T drivers' insurance |
| GET | `/api/settings/payment-card` | Fetch masked payment card (last 4, brand, no CVV) |
| PUT | `/api/settings/payment-card` | Encrypt and store payment card |
| POST | `/api/permits/order` | Queue batch permit automation job |
| GET | `/api/permits/status/{job_id}` | Poll job status from Redis |
| POST | `/api/orders/{job_id}/captcha-solved` | Signal CAPTCHA completion |
| GET | `/api/permits/history` | Fetch permit history |
| GET | `/api/permits/blankets` | Stub — returns empty array |
| GET | `/api/permits/form-fields` | Dynamic form field schemas per state/type |

### Data Flow (permit ordering)
1. Frontend sends `POST /api/permits/order` with `{driverIds, states, permitType, effectiveDate, effectiveTime, extraFields}`
2. FastAPI looks up full driver records from Supabase, builds permit objects with insurance/USDOT (company defaults for F/LP/T types, driver's own for owner-operators)
3. Inserts permit rows into Supabase as "Pending", fires Celery task, returns `jobId`
4. Frontend polls `GET /api/permits/status/{jobId}` every 3 seconds
5. Celery worker fetches decrypted payment card from Supabase, dispatches to state-specific runner via `SCRIPT_REGISTRY`
6. Runner fills DMV portal forms; some states (MS) proceed through payment with the encrypted card
7. If CAPTCHA appears: job pauses (`waiting_captcha`), user solves in browser, signals via `POST /api/orders/{jobId}/captcha-solved`

### Payment Card Security
- Card data is **never** stored in localStorage or plaintext
- Frontend sends card to `PUT /api/settings/payment-card` → backend encrypts with Fernet (AES) → stored as ciphertext in Supabase `settings` table
- `GET /api/settings/payment-card` returns masked data only (last 4 digits, brand, no CVV, no full number)
- Full card is decrypted only inside the Celery worker at job time, passed in-memory to Playwright runners
- Encryption key: `CARD_ENCRYPTION_KEY` env var (Fernet key, generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)

### CAPTCHA Modes
- `CAPTCHA_MODE=terminal` — Celery terminal blocks on `input()` (local dev)
- `CAPTCHA_MODE=dashboard` — polls Redis for signal from the frontend (production)

## Database Tables (Supabase)

### `fleet` — Driver/vehicle records
Key columns: `id`, `First Name`, `Last Name`, `Tractor Number`, `Driver Type`, `Year`, `Make`, `model`, `VIN (Serial Number)`, `Tag #`, `Tag State`, `Driver Code`, `USDOT`, `FEIN`, insurance fields, `active` (soft-delete flag). Column names have spaces — `database.py` COLUMN_MAP handles translation to camelCase.

### `permits` — Permit order history
Key columns: `id` (P0001 format), `job_id`, `driver_id`, `driver_name`, `tractor`, `state`, `permit_type`, `type`, `status` (Pending/Active/failed), `eff_date`, `exp_date`, `fee`, `created_at`.

### `settings` — Encrypted key-value config
Key columns: `key` (PK), `value` (Fernet ciphertext), `updated_at`. Currently stores `payment_card` only.

## State Scripts

**Supported states** (config.py): GA, FL, SC, NC, TN, AL, MS, LA, TX, AR

**Implemented scripts** (7 runners across 5 states):

| State | Script | Permit Types | Payment? | Notes |
|-------|--------|-------------|----------|-------|
| AL | `alabama_tf/runner.py` | trip, fuel, trip_fuel | No | CapSolver CAPTCHA integration; 3-page form |
| AL | `alabama_osow/runner.py` | os_ow | No | Login required (AL_USERNAME/AL_PASSWORD) |
| GA | `georgia_tf/runner.py` | trip, fuel, trip_fuel | No | Login required; twin forms for trip_fuel; has `transforms.py` |
| GA | `georgia_osow/runner.py` | os_ow | No | Scaffold only — logs in, navigates to form, stops at contact info |
| AR | `arkansas_trip/runner.py` | trip | No | No login; 7-step form; stops at payment method |
| FL | `florida_trip/runner.py` | trip, fuel, trip_fuel, fl_blanket_* | No | Login required; handles all FL permit types; FL defaults from `fl_permit_defaults.json` |
| MS | `mississippi_trip/runner.py` | trip (72 Hour Legal Trip) | Yes | Login required (MS_MDOT_USERNAME/MS_MDOT_PASSWORD); fills payment via encrypted card from settings; NIC USA secure checkout |

**Not implemented** (5 states): SC, NC, TN, LA, TX — listed in `SUPPORTED_STATES` but have no runner scripts.

All scripts: `chromium.launch(headless=False)` with `--disable-blink-features=AutomationControlled`.

### Script Registry (tasks.py)
```python
SCRIPT_REGISTRY = {
    ("AL", "trip_fuel"): run_alabama_tf,
    ("AL", "trip"):      run_alabama_tf,
    ("AL", "fuel"):      run_alabama_tf,
    ("AL", "os_ow"):     run_alabama_osow,
    ("GA", "trip_fuel"): run_georgia_tf,
    ("GA", "trip"):      run_georgia_tf,
    ("GA", "fuel"):      run_georgia_tf,
    ("GA", "os_ow"):     run_georgia_osow,
    ("AR", None):        run_arkansas_trip,
    ("FL", "trip"):                    run_florida_trip,
    ("FL", "fuel"):                    run_florida_trip,
    ("FL", "trip_fuel"):               run_florida_trip,
    ("FL", "fl_blanket_bulk"):         run_florida_trip,
    ("FL", "fl_blanket_inner_bridge"): run_florida_trip,
    ("FL", "fl_blanket_flatbed"):      run_florida_trip,
    ("MS", None):                      run_mississippi_trip,
}
```

## Data Ownership

The dashboard sends **only** driver IDs, state codes, permit type, effective date/time, and optional extra fields (dimensions, axle config for FL/GA OS/OW). All permit form data (VIN, USDOT, insurance, carrier details) is resolved server-side from Supabase. The frontend never holds or sends sensitive driver data. Payment card data is encrypted at rest and decrypted only in the Celery worker.

## Adding a New State

1. Create `backend/scripts/<state>/runner.py` with `run(permit, job_id, on_captcha_needed, company, payment_card)` function
2. Import and register in `tasks.py` `SCRIPT_REGISTRY` — use `(state, None)` tuple if one runner handles all permit types, or explicit `(state, type)` entries
3. Add state code to `SUPPORTED_STATES` in `config.py`
4. Add state to `STATES` array in `src/api.js`
5. If the state has dynamic form fields (dimensions, axles), add field schemas to `form_fields.py`
6. If the state has default values, add them to `fl_permit_defaults.json` (or a new defaults file)
7. Add any portal credentials to `.env`
8. Restart Celery worker

## Environment Variables (backend/.env)

### Required
- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` — Supabase project connection
- `REDIS_URL` — Redis broker (default: `redis://localhost:6379/0`)
- `JWT_SECRET` — JWT signing key (any strong random string)
- `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD` — shared login credentials
- `CARD_ENCRYPTION_KEY` — Fernet key for payment card encryption

### Per-state portal credentials
- Georgia: `GA_PORTAL_USERNAME`, `GA_PORTAL_PASSWORD`, `GA_ACCOUNT_NO`, `GA_OSOW_USERNAME`, `GA_OSOW_PASSWORD`
- Alabama: `AL_USERNAME`, `AL_PASSWORD`
- Florida: `FL_PORTAL_USERNAME`, `FL_PORTAL_PASSWORD`
- Mississippi: `MS_MDOT_USERNAME`, `MS_MDOT_PASSWORD`

### Optional
- `CAPSOLVER_API_KEY` — Alabama TAP CAPTCHA auto-solving
- `CAPTCHA_MODE` — `terminal` (local dev) or `dashboard` (production)

## Key Conventions

- Backend `.env` has Supabase credentials and portal logins — never commit it (`.env.example` exists)
- Frontend `API_BASE` in `src/api.js` points to `http://127.0.0.1:8000` — change only for production
- Supabase `fleet` table uses human-readable column names with spaces (e.g., `"Tractor Number"`); `database.py` COLUMN_MAP handles translation
- Company driver types (`F`, `LP`, `T`) use shared insurance/USDOT; owner-operators must have their own insurance fields in Supabase
- FastAPI CORS allows any localhost port via regex `r"http://(localhost|127\.0\.0\.1):\d+"` — update for production domain
- Tailwind theme: dark industrial with custom palette — navy (#0D1B2A), gold accent (#f0a500). Fonts: DM Sans (body), DM Mono (monospace). See `tailwind.config.js` for full color tokens.
- Drivers are soft-deleted (active=False), never removed from Supabase
- Permit IDs are sequential (P0001–P9999+), pre-generated in batches to avoid duplicates
- Insurance fields are conditionally shown in OrderForm only when GA is selected; auto-populated with Mega defaults for company drivers, blank for owner-operators
- FL permit defaults (dimensions, axles, load config) are loaded from `fl_permit_defaults.json` when a Florida permit type is selected

## Pre-Deployment TODOs

- [ ] Switch Playwright to `headless=True` for server deployment
- [ ] Update CORS `allow_origin_regex` in `app.py` for production domain
- [ ] Update `API_BASE` in `src/api.js` for production URL
- [ ] Add individual user accounts with bcrypt-hashed passwords (replace shared credential)
- [ ] Create Dockerfile for backend (FastAPI + Celery share same image)
- [ ] Set up CI/CD pipeline
- [ ] Implement remaining state scripts: SC, NC, TN, LA, TX
- [ ] Complete GA OS/OW runner (currently scaffold only)
- [ ] Add health check endpoint for load balancer
