from pydantic import BaseModel
from typing import Optional


# ── Request Models ───────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class MegaInsuranceRequest(BaseModel):
    insuranceCompany: Optional[str] = None
    insuranceEffective: Optional[str] = None
    insuranceExpiration: Optional[str] = None
    policyNumber: Optional[str] = None


class PermitOrderRequest(BaseModel):
    driverIds: list[int]
    states: list[str]
    permitType: str
    effectiveDate: Optional[str] = None  # null/empty for FL Flatbed (runner computes it)
    extraFields: Optional[dict] = None  # dynamic fields from backend form schema
    effectiveTime: Optional[str] = "12:00"


class CaptchaSolvedRequest(BaseModel):
    pass  # empty body, the signal is the POST itself


class DriverCreateRequest(BaseModel):
    firstName: str
    lastName: str
    tractor: str
    driverType: str
    year: Optional[int] = None
    make: Optional[str] = None
    vin: Optional[str] = None
    tagNumber: Optional[str] = None
    tagState: Optional[str] = None
    driverCode: Optional[str] = None
    usdot: Optional[str] = None
    fein: Optional[str] = None
    insuranceCompany: Optional[str] = None
    insuranceEffective: Optional[str] = None
    insuranceExpiration: Optional[str] = None
    policyNumber: Optional[str] = None


class DriverUpdateRequest(BaseModel):
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    tractor: Optional[str] = None
    driverType: Optional[str] = None
    year: Optional[int] = None
    make: Optional[str] = None
    vin: Optional[str] = None
    tagNumber: Optional[str] = None
    tagState: Optional[str] = None
    driverCode: Optional[str] = None
    usdot: Optional[str] = None
    fein: Optional[str] = None
    insuranceCompany: Optional[str] = None
    insuranceEffective: Optional[str] = None
    insuranceExpiration: Optional[str] = None
    policyNumber: Optional[str] = None


# ── Response Models ──────────────────────────────────────────────────

class PermitOrderResponse(BaseModel):
    jobId: str
    queued: int
    message: str


class JobStatusResponse(BaseModel):
    jobId: str
    status: str  # processing | complete | failed | waiting_captcha
    results: list[dict]
    summary: Optional[dict] = None


class ErrorResponse(BaseModel):
    error: str
