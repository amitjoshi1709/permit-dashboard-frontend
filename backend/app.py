import uuid
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from models import (
    LoginRequest,
    MegaInsuranceRequest,
    PaymentCardUpdate,
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
    get_mega_insurance,
    update_mega_insurance,
    get_payment_card,
    save_payment_card,
)
from tasks import run_permit_job, get_job_status, signal_captcha_solved
from config import SUPPORTED_STATES, VALID_PERMIT_TYPES, COMPANY_TYPES, COMPANY_DRIVER_DEFAULTS
from form_fields import get_merged_fields
from auth import verify_credentials, create_token, require_auth

app = FastAPI(title="Mega Trucking Permit API")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Authentication ───────────────────────────────────────────────────

@app.post("/api/auth/login")
def login(body: LoginRequest):
    if not verify_credentials(body.username, body.password):
        raise HTTPException(401, "Invalid username or password")
    return {"token": create_token(body.username), "username": body.username}


@app.get("/api/auth/me")
def me(user: str = Depends(require_auth)):
    return {"username": user}


# ── Drivers ──────────────────────────────────────────────────────────

@app.get("/api/drivers")
def list_drivers(_: str = Depends(require_auth)):
    return get_active_drivers()


@app.post("/api/drivers")
def create_driver(body: DriverCreateRequest, _: str = Depends(require_auth)):
    return create_driver_record(body.model_dump(exclude_none=True))


# NOTE: Mega insurance routes must be defined BEFORE the /{driver_id} routes
# so FastAPI matches the literal path first instead of trying to parse
# "mega-insurance" as an integer driver_id.
@app.get("/api/drivers/mega-insurance")
def read_mega_insurance(_: str = Depends(require_auth)):
    return get_mega_insurance()


@app.put("/api/drivers/mega-insurance")
def put_mega_insurance(body: MegaInsuranceRequest, _: str = Depends(require_auth)):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "No fields to update")
    updated = update_mega_insurance(data)
    return {"success": True, "updated": updated}


@app.put("/api/drivers/{driver_id}")
def update_driver(driver_id: int, body: DriverUpdateRequest, _: str = Depends(require_auth)):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "No fields to update")
    return update_driver_record(driver_id, data)


@app.delete("/api/drivers/{driver_id}")
def delete_driver(driver_id: int, _: str = Depends(require_auth)):
    ok = soft_delete_driver(driver_id)
    if not ok:
        raise HTTPException(404, "Driver not found")
    return {"success": True}


# ── Payment Card (encrypted) ────────────────────────────────────────

@app.get("/api/settings/payment-card")
def read_payment_card(_: str = Depends(require_auth)):
    return get_payment_card()


@app.put("/api/settings/payment-card")
def put_payment_card(body: PaymentCardUpdate, _: str = Depends(require_auth)):
    card_data = body.model_dump()
    card_data["cardNumber"] = card_data["cardNumber"].replace(" ", "")
    save_payment_card(card_data)
    return {"success": True}


# ── Permit Ordering ──────────────────────────────────────────────────

@app.post("/api/permits/order")
def order_permits(body: PermitOrderRequest, _: str = Depends(require_auth)):
    # Validate states
    for s in body.states:
        if s not in SUPPORTED_STATES:
            raise HTTPException(400, f"State {s} is not currently supported")

    # Validate permit type
    if body.permitType not in VALID_PERMIT_TYPES:
        raise HTTPException(400, "Invalid permit type")

    # Fetch driver records. Supabase's `.in_()` dedupes IDs, so re-expand the
    # list to honor duplicates: if the user asked for the same driver twice
    # (e.g. via History → Duplicate), we want two permits, not one.
    unique_drivers = get_drivers_by_ids(list(set(body.driverIds)))
    if not unique_drivers:
        raise HTTPException(400, "No valid driver IDs provided")
    by_id = {d["id"]: d for d in unique_drivers}
    drivers = [by_id[did] for did in body.driverIds if did in by_id]

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

                # Build insurance object — always read from Supabase.
                # Mega drivers (F/LP/T) all share the same values; updating
                # them via the Driver Database tab updates every Mega row.
                insurance = {
                    "company": driver.get("insuranceCompany", ""),
                    "effectiveDate": driver.get("insuranceEffective", ""),
                    "expirationDate": driver.get("insuranceExpiration", ""),
                    "policyNumber": driver.get("policyNumber", ""),
                }
                # USDOT: company drivers share Mega's DOT number; owner-ops use their own.
                if driver.get("driverType") in COMPANY_TYPES:
                    usdot = COMPANY_DRIVER_DEFAULTS["usdot"]
                else:
                    usdot = driver.get("usdot", "")

                # Supabase row — inserted as Pending before automation runs.
                # `extra_fields` stores the exact POST payload (dimensions, axles, etc.)
                # so the History "Duplicate" feature can resend identical values for FL.
                permit_rows.append({
                    "id": permit_id,
                    "job_id": job_id,
                    "driver_id": driver["id"],
                    "driver_name": driver_name,
                    "tractor": driver["tractor"],
                    "state": state,
                    "permit_type": expanded_type,
                    "status": "Pending",
                    "eff_date": body.effectiveDate or "",
                    "fee": 0,
                    "extra_fields": body.extraFields,
                })

                permit_data = {
                    "permitId": permit_id,
                    "state": state,
                    "permitType": expanded_type,
                    "effectiveDate": body.effectiveDate or "",
                    "effectiveTime": body.effectiveTime or "12:00",
                    "extraFields": body.extraFields,
                    "driver": {
                        "firstName": driver["firstName"],
                        "lastName": driver["lastName"],
                        "driverType": driver.get("driverType", ""),
                        "driverCode": driver.get("driverCode", ""),
                        "tractor": driver["tractor"],
                        "year": driver.get("year"),
                        "make": driver.get("make", ""),
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
def poll_job_status(job_id: str, _: str = Depends(require_auth)):
    status = get_job_status(job_id)
    if status is None:
        raise HTTPException(404, f"Job {job_id} not found")
    return status


# ── CAPTCHA Signal ───────────────────────────────────────────────────

@app.post("/api/orders/{job_id}/captcha-solved")
def captcha_solved(job_id: str, permit_id: str = "", _: str = Depends(require_auth)):
    signal_captcha_solved(job_id, permit_id)
    return {"success": True}


# ── Permit History & Blankets ────────────────────────────────────────
# TODO: These will query a permits table once it exists.
# For now, return empty arrays so the frontend doesn't break.

@app.get("/api/permits/history")
def permit_history(_: str = Depends(require_auth)):
    return get_permit_history()


@app.get("/api/permits/form-fields")
def get_form_fields(states: str, permitType: str, _: str = Depends(require_auth)):
    """Return dynamic field schema for the given states + permit type."""
    state_list = [s.strip() for s in states.split(",") if s.strip()]
    return {"fields": get_merged_fields(state_list, permitType)}


@app.get("/api/permits/blankets")
def blanket_permits(_: str = Depends(require_auth)):
    # TODO: Query blanket_permits table from Supabase
    return []
