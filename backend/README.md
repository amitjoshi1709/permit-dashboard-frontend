# Permit Dashboard — FastAPI Backend

Backend server for Mega Trucking's permit ordering dashboard. Handles driver data from Supabase, queues permit automation jobs through Celery + Redis, and runs Playwright scripts against state DMV portals.

---

## Architecture Overview

```
Frontend (React + Vite, port 5173)
    |
    |  HTTP requests
    v
FastAPI (port 8000)
    |
    |  Celery task dispatch
    v
Redis (port 6379) ---- message broker + job status store
    |
    v
Celery Worker
    |
    |  Imports state-specific runner
    v
scripts/alabama/runner.py  (Playwright automation)
scripts/georgia/runner.py  (future)
scripts/<state>/runner.py  (add more here)
```

**Three processes must be running:**
1. Redis (Docker container)
2. FastAPI server (uvicorn)
3. Celery worker

---

## Prerequisites

- **Python 3.12+**
- **Docker Desktop** (for Redis)
- **Node.js 18+** (for the frontend — separate repo concern)
- A **Supabase** project with a `fleet` table containing driver/truck data

---

## File Structure

```
backend/
  app.py             # FastAPI — all HTTP endpoints
  celery_app.py      # Celery instance + config
  tasks.py           # Background job definitions + Redis helpers
  config.py          # Company constants (address, email, USDOT, insurance)
  database.py        # Supabase client + query functions
  models.py          # Pydantic request/response models
  requirements.txt   # Python dependencies
  .env               # Environment variables (DO NOT COMMIT)
  scripts/
    __init__.py
    alabama/
      __init__.py
      runner.py      # Playwright automation for Alabama DMV TAP portal
    georgia/
      __init__.py
      runner.py      # (future) Georgia automation
```

---

## Setup

### 1. Clone and navigate

```bash
git clone <repo-url>
cd permit-dashboard/backend
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv

# Windows (PowerShell)
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Playwright browsers

```bash
playwright install chromium
```

### 5. Create your `.env` file

Copy this and fill in your Supabase credentials:

```env
# ── Supabase ──────────────────────────────────────────
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIs...your-service-role-key

# ── Redis ─────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0

# ── CAPTCHA Handling ──────────────────────────────────
# "terminal"  = solve CAPTCHA in browser, press ENTER in Celery terminal (local testing)
# "dashboard" = solve CAPTCHA in browser, click Continue in the dashboard (production)
CAPTCHA_MODE=terminal
```

> **Where to find Supabase keys:**
> Supabase Dashboard > Project Settings > API
> - `SUPABASE_URL` = Project URL
> - `SUPABASE_SERVICE_KEY` = service_role key (NOT the anon key)

### 6. Supabase `fleet` table

The backend reads from a table called `fleet`. Required columns:

| Column Name               | Type    | Example                  |
|---------------------------|---------|--------------------------|
| id                        | int8    | 1                        |
| First Name                | text    | ROBERTO                  |
| Last Name                 | text    | ACEVEDO VILLAFANE        |
| Tractor Number            | text    | F1480                    |
| Driver Type               | text    | F                        |
| Driver Code               | text    | EJAGUIAR                 |
| Year                      | int4    | 2006                     |
| Make                      | text    | FREIGHTLINER             |
| VIN (Serial Number)       | text    | 1FUJA6CK66LW30560       |
| Tag #                     | text    | JSRR42                   |
| Tag State                 | text    | FL                       |
| USDOT                     | text    | 2582238                  |
| FEIN                      | text    | (nullable)               |
| Insurance Company         | text    | (nullable, for O/O only) |
| Insurance Effective Date  | text    | (nullable, for O/O only) |
| Insurance Expiration Date | text    | (nullable, for O/O only) |
| Insurance Policy Number   | text    | (nullable, for O/O only) |
| active                    | bool    | true                     |

> **Driver types F, LP, T** are company drivers — the backend auto-fills company insurance and USDOT from `config.py`. Owner-operators (O/O) must have their own insurance fields filled in.

---

## Running the Backend

You need **three terminals** open simultaneously:

### Terminal 1 — Start Redis

```bash
docker start zealous_hodgkin
```

Or if you don't have a Redis container yet:

```bash
docker run -d -p 6379:6379 --name redis redis:alpine
```

### Terminal 2 — Start FastAPI

```bash
cd backend
uvicorn app:app --reload --port 8000
```

Server runs at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

### Terminal 3 — Start Celery Worker

```bash
cd backend

# Windows PowerShell
celery -A celery_app worker --loglevel=info --pool=solo

# Mac/Linux
CAPTCHA_MODE=terminal celery -A celery_app worker --loglevel=info --pool=solo
```

> **Important:** On Windows, Celery requires `--pool=solo` (the default prefork pool doesn't work on Windows).

---

## API Endpoints

| Method | Endpoint                              | Purpose                          |
|--------|---------------------------------------|----------------------------------|
| GET    | `/api/drivers`                        | List all active drivers          |
| POST   | `/api/drivers`                        | Create a new driver              |
| PUT    | `/api/drivers/{id}`                   | Update a driver                  |
| DELETE | `/api/drivers/{id}`                   | Soft-delete a driver             |
| POST   | `/api/permits/order`                  | Start a permit automation job    |
| GET    | `/api/permits/status/{job_id}`        | Poll job status                  |
| POST   | `/api/orders/{job_id}/captcha-solved` | Signal CAPTCHA solved            |
| GET    | `/api/permits/history`                | Get permit history (TODO)        |
| GET    | `/api/permits/blankets`               | Get blanket permits (TODO)       |

### POST `/api/permits/order` — Request body

```json
{
  "driverIds": [1, 5, 12],
  "states": ["AL"],
  "permitType": "trip_fuel",
  "effectiveDate": "2026-03-25"
}
```

Valid `permitType` values: `trip_fuel`, `trip`, `fuel`, `os_ow`

### POST `/api/permits/order` — Response

```json
{
  "jobId": "JOB-4193EB4D",
  "queued": 3,
  "message": "Permits queued. Automation will stop before payment."
}
```

### GET `/api/permits/status/{job_id}` — Response

```json
{
  "jobId": "JOB-4193EB4D",
  "status": "processing",
  "results": [
    {
      "permitId": "P0001",
      "driverName": "ROBERTO ACEVEDO VILLAFANE",
      "tractor": "F1480",
      "permitType": "trip_fuel",
      "status": "success",
      "message": "Reached payment page"
    }
  ],
  "summary": null
}
```

Job status values:
- `processing` — automation running
- `waiting_captcha` — paused at CAPTCHA, waiting for user
- `complete` — all permits done
- `failed` — all permits failed

---

## How the Automation Flow Works

1. User selects driver(s), state, permit type, and effective date in the dashboard
2. Dashboard sends `POST /api/permits/order`
3. FastAPI looks up full driver details from Supabase, builds permit objects, fires a Celery task, returns a job ID immediately
4. Dashboard starts polling `GET /api/permits/status/{job_id}` every 3 seconds
5. Celery worker picks up the job, looks up the state in `SCRIPT_REGISTRY`, launches Playwright
6. The automation fills the DMV form step by step and **stops before payment**
7. If a CAPTCHA appears, the job pauses — the user solves it in the browser window, then clicks "Continue" in the dashboard
8. Dashboard sends `POST /api/orders/{job_id}/captcha-solved`, Celery resumes

---

## CAPTCHA Handling (Local Testing)

When `CAPTCHA_MODE=terminal` (the default):

1. The automation opens a visible Chrome window and navigates to the DMV portal
2. When it hits the CAPTCHA page, the Celery terminal prints:
   ```
   ====================================
     Solve the CAPTCHA in the browser window,
     then press ENTER here to continue.
   ========================================
   ```
3. Go to the browser window, solve the CAPTCHA
4. Come back to the Celery terminal and press ENTER
5. The automation continues filling the form

---

## Adding a New State

1. Create `scripts/<state>/__init__.py` (empty file)
2. Create `scripts/<state>/runner.py` with a `run()` function:
   ```python
   def run(permit: dict, job_id: str, on_captcha_needed=None, company: dict = None) -> dict:
       # permit["driver"] has all driver/vehicle details
       # company has legal name, address, email, etc.
       # on_captcha_needed() blocks until CAPTCHA is solved
       # Return {"permitId": ..., "status": "success"/"error", "message": ...}
   ```
3. Register it in `tasks.py`:
   ```python
   from scripts.georgia.runner import run as run_georgia

   SCRIPT_REGISTRY = {
       "AL": run_alabama,
       "GA": run_georgia,  # <-- add this line
   }
   ```
4. Restart the Celery worker

No other files need to change.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Cannot connect to redis://localhost:6379` | Redis isn't running. Run `docker start <container-name>` or `docker run -d -p 6379:6379 --name redis redis:alpine` |
| `Received unregistered task` | Restart the Celery worker after any code changes to `tasks.py` |
| `No module named 'config'` | Make sure you're running Celery from the `backend/` directory |
| `proxy` TypeError on startup | httpx version conflict. Run `pip install httpx>=0.27.0` |
| Celery hangs on Windows | Must use `--pool=solo` flag |
| CAPTCHA not pausing | Check `CAPTCHA_MODE` env var. Default is `terminal` |
| Frontend can't connect | FastAPI must run on port 8000. Check CORS in `app.py` allows your frontend origin |

---

## Production Notes

- Replace `--pool=solo` with `--pool=prefork` or `--pool=gevent` on Linux servers
- Set `CAPTCHA_MODE=dashboard` so CAPTCHA signals come from the frontend, not the terminal
- Update `allow_origins` in `app.py` to your production frontend URL
- Redis should be a managed instance (AWS ElastiCache, etc.), not a local Docker container
- Each Celery worker handles one Playwright browser at a time (by design — `worker_prefetch_multiplier=1`)
- Scale by running multiple Celery workers on different machines
