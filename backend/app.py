import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import (
    PermitOrderRequest,
    PermitOrderResponse,
    DriverCreateRequest,
    DriverUpdateRequest,
    ErrorResponse,
)
from database import (
    get_active_drivers,
    get_drivers_by_ids,
    create_driver_record,
    update_driver_record,
    soft_delete_driver,
    generate_permit_ids,
    insert_permits,
    update_permit_status,
    get_permit_history,
)
from tasks import run_permit_job, get_job_status, signal_captcha_solved
from config import SUPPORTED_STATES, VALID_PERMIT_TYPES, COMPANY_TYPES, COMPANY_DRIVER_DEFAULTS
from form_fields import get_merged_fields

app = FastAPI(title="Mega Trucking Permit API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


# ── Drivers ──────────────────────────────────────────────────────────

@app.get("/api/drivers")
def list_drivers():
    return get_active_drivers()


@app.post("/api/drivers")
def create_driver(body: DriverCreateRequest):
    return create_driver_record(body.model_dump(exclude_none=True))


@app.put("/api/drivers/{driver_id}")
def update_driver(driver_id: int, body: DriverUpdateRequest):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "No fields to update")
    return update_driver_record(driver_id, data)


@app.delete("/api/drivers/{driver_id}")
def delete_driver(driver_id: int):
    ok = soft_delete_driver(driver_id)
    if not ok:
        raise HTTPException(404, "Driver not found")
    return {"success": True}


# ── Permit Ordering ──────────────────────────────────────────────────

@app.post("/api/permits/order")
def order_permits(body: PermitOrderRequest):
    # Validate states
    for s in body.states:
        if s not in SUPPORTED_STATES:
            raise HTTPException(400, f"State {s} is not currently supported")

    # Validate permit type
    if body.permitType not in VALID_PERMIT_TYPES:
        raise HTTPException(400, "Invalid permit type")

    # Fetch driver records
    drivers = get_drivers_by_ids(body.driverIds)
    if not drivers:
        raise HTTPException(400, "No valid driver IDs provided")

    # For states with separate trip/fuel forms, split "trip_fuel" into two
    # permits so they're tracked and processed independently by the queue.
    SPLIT_TRIP_FUEL_STATES = {"GA"}

    def expand_permit_types(state: str, permit_type: str) -> list[str]:
        if state in SPLIT_TRIP_FUEL_STATES and permit_type == "trip_fuel":
            return ["trip", "fuel"]
        return [permit_type]

    # Build automation permits list (driver × state × expanded-type combinations)
    job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"
    permits = []
    permit_rows = []

    # Pre-generate all permit IDs in one query to avoid duplicates
    total_permits = sum(
        len(expand_permit_types(state, body.permitType))
        for _ in drivers
        for state in body.states
    )
    permit_ids = generate_permit_ids(total_permits)
    id_index = 0

    for driver in drivers:
        for state in body.states:
            for expanded_type in expand_permit_types(state, body.permitType):
                permit_id = permit_ids[id_index]
                id_index += 1
                driver_name = f"{driver['lastName']}, {driver['firstName']}"

                # Build insurance object
                if driver.get("driverType") in COMPANY_TYPES:
                    insurance = {
                        "company": COMPANY_DRIVER_DEFAULTS["insurance_company"],
                        "effectiveDate": COMPANY_DRIVER_DEFAULTS["insurance_effective"],
                        "expirationDate": COMPANY_DRIVER_DEFAULTS["insurance_expiration"],
                        "policyNumber": COMPANY_DRIVER_DEFAULTS["policy_number"],
                    }
                    usdot = COMPANY_DRIVER_DEFAULTS["usdot"]
                else:
                    insurance = {
                        "company": driver.get("insuranceCompany", ""),
                        "effectiveDate": driver.get("insuranceEffective", ""),
                        "expirationDate": driver.get("insuranceExpiration", ""),
                        "policyNumber": driver.get("policyNumber", ""),
                    }
                    usdot = driver.get("usdot", "")

                # Supabase row — inserted as Pending before automation runs
                permit_rows.append({
                    "id": permit_id,
                    "job_id": job_id,
                    "driver_id": driver["id"],
                    "driver_name": driver_name,
                    "tractor": driver["tractor"],
                    "state": state,
                    "permit_type": expanded_type,
                    "status": "Pending",
                    "eff_date": body.effectiveDate,
                    "fee": 0,
                })

                permit_data = {
                    "permitId": permit_id,
                    "state": state,
                    "permitType": expanded_type,
                    "effectiveDate": body.effectiveDate or "",
                "extraFields": body.extraFields,
                    "effectiveTime": body.effectiveTime or "12:00",
                    "driver": {
                        "firstName": driver["firstName"],
                        "lastName": driver["lastName"],
                        "driverType": driver.get("driverType", ""),
                        "driverCode": driver.get("driverCode", ""),
                        "tractor": driver["tractor"],
                        "year": driver.get("year"),
                        "make": driver.get("make", ""),
                    "model": driver.get("model", ""),
                        "model": driver.get("model", ""),
                        "vin": driver.get("vin", ""),
                        "tagNumber": driver.get("tagNumber", ""),
                        "tagState": driver.get("tagState", ""),
                        "usdot": usdot,
                        "fein": driver.get("fein", ""),
                        "insurance": insurance,
                    },
                }
                permits.append(permit_data)

    # Insert permits into Supabase as Pending
    insert_permits(permit_rows)

    # Fire Celery background task
    run_permit_job.delay(job_id, permits)

    return PermitOrderResponse(
        jobId=job_id,
        queued=len(permits),
        message="Permits queued. Automation will stop before payment.",
    )


# ── Job Status Polling ───────────────────────────────────────────────

@app.get("/api/permits/status/{job_id}")
def poll_job_status(job_id: str):
    status = get_job_status(job_id)
    if status is None:
        raise HTTPException(404, f"Job {job_id} not found")
    return status


# ── CAPTCHA Signal ───────────────────────────────────────────────────

@app.post("/api/orders/{job_id}/captcha-solved")
def captcha_solved(job_id: str, permit_id: str = ""):
    signal_captcha_solved(job_id, permit_id)
    return {"success": True}


# ── Permit History & Blankets ────────────────────────────────────────
# TODO: These will query a permits table once it exists.
# For now, return empty arrays so the frontend doesn't break.

@app.get("/api/permits/history")
def permit_history():
    return get_permit_history()


@app.get("/api/permits/form-fields")
def get_form_fields(states: str, permitType: str):
    """Return dynamic field schema for the given states + permit type."""
    state_list = [s.strip() for s in states.split(",") if s.strip()]
    return {"fields": get_merged_fields(state_list, permitType)}


@app.get("/api/permits/blankets")
def blanket_permits():
    # TODO: Query blanket_permits table from Supabase
    return []
