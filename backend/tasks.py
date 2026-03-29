"""
Celery tasks — one task per state script (scalable registry pattern).

Adding a new state:
  1. Write scripts/<state>/runner.py with a run(permit, job_id, on_captcha_needed) function.
  2. Import it here and add an entry to SCRIPT_REGISTRY.
  3. That's it — no other file changes needed.
"""

import json
import time
import os
import redis
from celery_app import celery
from dotenv import load_dotenv
from database import update_permit_status

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)

# ── Script Registry ──────────────────────────────────────────────────

from config import COMPANY
from scripts.alabama.runner import run as run_alabama
from scripts.georgia.runner import run as run_georgia

SCRIPT_REGISTRY = {
    "AL": run_alabama,
    "GA": run_georgia,
    # "FL": run_florida,
    # "TX": run_texas,
    # ...add new states here
}


# ── Redis helpers ────────────────────────────────────────────────────

def get_job_key(job_id: str) -> str:
    return f"job:{job_id}"


def set_job_status(job_id: str, status: str, results: list = None, summary: dict = None):
    """Write current job state to Redis so the polling endpoint can read it."""
    data = {
        "jobId": job_id,
        "status": status,
        "results": results or [],
        "summary": summary,
    }
    r.set(get_job_key(job_id), json.dumps(data), ex=3600)  # expire after 1 hour


def get_job_status(job_id: str) -> dict | None:
    raw = r.get(get_job_key(job_id))
    if raw is None:
        return None
    return json.loads(raw)


def signal_captcha_solved(job_id: str, permit_id: str = ""):
    """Called by the API when the user clicks 'Continue' after solving CAPTCHA."""
    key = f"captcha:{job_id}"
    r.set(key, "1", ex=600)


# ── CAPTCHA callback factory ─────────────────────────────────────────

def _make_captcha_callback(job_id: str, permit_id: str, current_results: list):
    """
    Returns a callback function that the runner calls when it hits a CAPTCHA.

    CAPTCHA_MODE=terminal (default for local testing):
      Prints a message in the Celery terminal and waits for ENTER.

    CAPTCHA_MODE=dashboard (production):
      Sets job status to 'waiting_captcha' and polls Redis until
      the dashboard hits POST /orders/{job_id}/captcha-solved.
    """
    mode = os.getenv("CAPTCHA_MODE", "terminal")

    def on_captcha_needed():
        if mode == "terminal":
            set_job_status(job_id, "waiting_captcha", current_results)
            print(f"\n[task:{job_id}] ====================================")
            print(f"  Solve the CAPTCHA in the browser window,")
            print(f"  then press ENTER here to continue.")
            print(f"========================================\n")
            input("  Press ENTER after solving CAPTCHA: ")
            set_job_status(job_id, "processing", current_results)
            return

        # Dashboard mode — poll Redis for signal from API
        set_job_status(job_id, "waiting_captcha", current_results)
        print(f"[task:{job_id}] Waiting for CAPTCHA signal from dashboard...")

        timeout = 300  # seconds
        start = time.time()
        key = f"captcha:{job_id}"
        while time.time() - start < timeout:
            if r.get(key):
                r.delete(key)
                set_job_status(job_id, "processing", current_results)
                print(f"[task:{job_id}] CAPTCHA solved — resuming.")
                return
            time.sleep(1)

        raise TimeoutError("CAPTCHA was not solved within 5 minutes.")

    return on_captcha_needed


# ── Celery Task ──────────────────────────────────────────────────────

@celery.task(bind=True, name="tasks.run_permit_job")
def run_permit_job(self, job_id: str, permits: list):
    """
    Background task: process a batch of permits.

    Each permit dict contains:
    {
        "permitId": "P0051",
        "state": "AL",
        "permitType": "trip_fuel",
        "effectiveDate": "2026-03-24",
        "driver": { ...full driver details from Supabase... }
    }
    """
    print(f"[task:{job_id}] Starting permit job — {len(permits)} permit(s)")
    results = []
    set_job_status(job_id, "processing", results)

    for permit in permits:
        state = permit["state"]
        runner = SCRIPT_REGISTRY.get(state)

        if not runner:
            results.append({
                "permitId": permit["permitId"],
                "driverName": f"{permit['driver']['firstName']} {permit['driver']['lastName']}",
                "tractor": permit["driver"]["tractor"],
                "permitType": permit.get("permitType", ""),
                "status": "error",
                "message": f"No automation script for state {state}",
            })
            set_job_status(job_id, "processing", results)
            continue

        try:
            captcha_cb = _make_captcha_callback(job_id, permit["permitId"], results)
            result = runner(permit, job_id, on_captcha_needed=captcha_cb, company=COMPANY)
            results.append(result)

            # Update Supabase: success → "Active" (reached payment page), error → "failed"
            db_status = "Active" if result["status"] == "success" else "failed"
            update_permit_status(permit["permitId"], db_status)
        except Exception as e:
            results.append({
                "permitId": permit["permitId"],
                "driverName": f"{permit['driver']['firstName']} {permit['driver']['lastName']}",
                "tractor": permit["driver"]["tractor"],
                "permitType": permit.get("permitType", ""),
                "status": "error",
                "message": str(e),
            })
            update_permit_status(permit["permitId"], "failed")

        set_job_status(job_id, "processing", results)

    # Build summary
    succeeded = sum(1 for res in results if res["status"] == "success")
    failed = len(results) - succeeded
    summary = {"total": len(results), "succeeded": succeeded, "failed": failed}

    final_status = "complete" if failed == 0 else ("failed" if succeeded == 0 else "complete")
    set_job_status(job_id, final_status, results, summary)
    print(f"[task:{job_id}] Done — {succeeded}/{len(results)} succeeded")
