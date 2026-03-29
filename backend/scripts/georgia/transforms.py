"""
Georgia Portal — Data Transforms & Validation

Ported from the Node.js transforms.js. Maps API payload fields
to the exact dropdown values and field formats the GA portal expects.
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# All 50 states + DC → GA portal dropdown format
# ---------------------------------------------------------------------------

STATE_DROPDOWN_MAP = {
    "AL": "AL - ALABAMA",
    "AK": "AK - ALASKA",
    "AZ": "AZ - ARIZONA",
    "AR": "AR - ARKANSAS",
    "CA": "CA - CALIFORNIA",
    "CO": "CO - COLORADO",
    "CT": "CT - CONNECTICUT",
    "DE": "DE - DELAWARE",
    "DC": "DC - DISTRICT OF COLUMBIA",
    "FL": "FL - FLORIDA",
    "GA": "GA - GEORGIA",
    "HI": "HI - HAWAII",
    "ID": "ID - IDAHO",
    "IL": "IL - ILLINOIS",
    "IN": "IN - INDIANA",
    "IA": "IA - IOWA",
    "KS": "KS - KANSAS",
    "KY": "KY - KENTUCKY",
    "LA": "LA - LOUISIANA",
    "ME": "ME - MAINE",
    "MD": "MD - MARYLAND",
    "MA": "MA - MASSACHUSETTS",
    "MI": "MI - MICHIGAN",
    "MN": "MN - MINNESOTA",
    "MS": "MS - MISSISSIPPI",
    "MO": "MO - MISSOURI",
    "MT": "MT - MONTANA",
    "NE": "NE - NEBRASKA",
    "NV": "NV - NEVADA",
    "NH": "NH - NEW HAMPSHIRE",
    "NJ": "NJ - NEW JERSEY",
    "NM": "NM - NEW MEXICO",
    "NY": "NY - NEW YORK",
    "NC": "NC - NORTH CAROLINA",
    "ND": "ND - NORTH DAKOTA",
    "OH": "OH - OHIO",
    "OK": "OK - OKLAHOMA",
    "OR": "OR - OREGON",
    "PA": "PA - PENNSYLVANIA",
    "RI": "RI - RHODE ISLAND",
    "SC": "SC - SOUTH CAROLINA",
    "SD": "SD - SOUTH DAKOTA",
    "TN": "TN - TENNESSEE",
    "TX": "TX - TEXAS",
    "UT": "UT - UTAH",
    "VT": "VT - VERMONT",
    "VA": "VA - VIRGINIA",
    "WA": "WA - WASHINGTON",
    "WV": "WV - WEST VIRGINIA",
    "WI": "WI - WISCONSIN",
    "WY": "WY - WYOMING",
}

# ---------------------------------------------------------------------------
# Vehicle make → GA portal dropdown value (case-insensitive lookup)
# ---------------------------------------------------------------------------

MAKE_DISPLAY_MAP = {
    # Full names
    "freightliner":  "FRHT - Freightliner",
    "peterbilt":     "PETE - Peterbilt",
    "mack":          "MACK - Mack",
    "kenworth":      "KW - Kenworth",
    "international": "IHC - International",
    "volvo":         "VOLV - Volvo",
    "western star":  "WSTR - Western Star",
    # Short codes (fallback if fleet DB uses codes)
    "frht":          "FRHT - Freightliner",
    "pete":          "PETE - Peterbilt",
    "kw":            "KW - Kenworth",
    "ihc":           "IHC - International",
    "volv":          "VOLV - Volvo",
    "intl":          "IHC - International",
    "wstr":          "WSTR - Western Star",
}

# ---------------------------------------------------------------------------
# API permitType → portal dropdown values
# "trip_fuel" means TWO separate permit forms per driver
# ---------------------------------------------------------------------------

PERMIT_TYPE_MAP = {
    "trip":          ["ITP - IRP TRIP PERMIT"],
    "fuel":          ["MFTP - MTTP PERMIT"],
    "trip_fuel":     ["ITP - IRP TRIP PERMIT", "MFTP - MTTP PERMIT"],
    "fuel_and_trip": ["ITP - IRP TRIP PERMIT", "MFTP - MTTP PERMIT"],
    "fuel and trip": ["ITP - IRP TRIP PERMIT", "MFTP - MTTP PERMIT"],
    "both":          ["ITP - IRP TRIP PERMIT", "MFTP - MTTP PERMIT"],
}


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def lookup_make(make: str) -> Optional[str]:
    """Case-insensitive make lookup. Returns portal dropdown value or None."""
    if not make:
        return None
    return MAKE_DISPLAY_MAP.get(make.lower().strip())


def iso_to_portal_date(iso_date: str) -> str:
    """
    Convert ISO date "2026-03-24" to portal format "03/24/2026".
    Also handles "MM/DD/YYYY" passthrough if already in that format.
    """
    if not iso_date:
        return ""
    # Already in MM/DD/YYYY format
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", iso_date):
        m, d, y = iso_date.split("/")
        return f"{m.zfill(2)}/{d.zfill(2)}/{y}"
    # ISO format YYYY-MM-DD
    parts = iso_date.split("-")
    if len(parts) != 3:
        return iso_date
    y, m, d = parts
    return f"{m.zfill(2)}/{d.zfill(2)}/{y}"


def normalize_date(date_str: str) -> str:
    """Ensure MM/DD/YYYY has zero-padded month and day."""
    parts = date_str.strip().split("/")
    if len(parts) != 3:
        return date_str
    m, d, y = parts
    return f"{m.zfill(2)}/{d.zfill(2)}/{y}"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_permit(permit: dict) -> list[str]:
    """
    Validate a permit object from the API payload.
    Returns a list of error strings (empty = valid).
    """
    errors = []
    if not permit:
        return ["Permit object is null/undefined"]

    if not permit.get("permitType"):
        errors.append("Missing permitType")
    else:
        normalized = permit["permitType"].lower().strip()
        if normalized not in PERMIT_TYPE_MAP:
            valid = ", ".join(PERMIT_TYPE_MAP.keys())
            errors.append(f'Unknown permitType: "{permit["permitType"]}". Valid: {valid}')

    if not permit.get("effectiveDate"):
        errors.append("Missing effectiveDate")

    d = permit.get("driver")
    if not d:
        errors.append("Missing driver object")
        return errors

    if not d.get("vin"):
        errors.append("Missing driver.vin")
    if not d.get("year"):
        errors.append("Missing driver.year")
    if not d.get("make"):
        errors.append("Missing driver.make")
    elif not lookup_make(d["make"]):
        known = ", ".join(MAKE_DISPLAY_MAP.keys())
        errors.append(f'Unknown make: "{d["make"]}". Known: {known}')
    if not d.get("tagState"):
        errors.append("Missing driver.tagState")
    elif d["tagState"].upper() not in STATE_DROPDOWN_MAP:
        errors.append(f'Unknown tagState: "{d["tagState"]}"')
    if not d.get("usdot"):
        errors.append("Missing driver.usdot")

    ins = d.get("insurance")
    if not ins:
        errors.append("Missing driver.insurance")
        return errors
    if not ins.get("company"):
        errors.append("Missing insurance.company")
    if not ins.get("effectiveDate"):
        errors.append("Missing insurance.effectiveDate")
    if not ins.get("expirationDate"):
        errors.append("Missing insurance.expirationDate")
    if not ins.get("policyNumber"):
        errors.append("Missing insurance.policyNumber")

    return errors


# ---------------------------------------------------------------------------
# Transform: API permit → portal-ready data dict(s)
# ---------------------------------------------------------------------------

def transform_permit(permit: dict, account_no: str = "82761") -> list[dict]:
    """
    Transform one API permit object into a list of portal-ready data dicts.
    Returns 1 dict for "trip" or "fuel", 2 dicts for "trip_fuel".
    """
    normalized_type = permit["permitType"].lower().strip()
    permit_types = PERMIT_TYPE_MAP.get(normalized_type)
    if not permit_types:
        raise ValueError(f'Unknown permitType: "{permit["permitType"]}"')

    d = permit["driver"]
    make_dropdown = lookup_make(d["make"])
    if not make_dropdown:
        raise ValueError(f'Unknown make: "{d["make"]}"')

    state_dropdown = STATE_DROPDOWN_MAP.get(d["tagState"].upper())
    if not state_dropdown:
        raise ValueError(f'Unknown tagState: "{d["tagState"]}"')

    results = []
    for portal_permit_type in permit_types:
        results.append({
            # Permit Details
            "account_no":            account_no,
            "permit_type":           portal_permit_type,
            "permit_eff_date":       iso_to_portal_date(permit["effectiveDate"]),

            # Motor Carrier
            "safety_usdot":          d["usdot"],

            # Vehicle Details
            "vin":                   d["vin"],
            "confirmed_vin":        d["vin"],
            "year":                  str(d["year"]),
            "make":                  make_dropdown,
            "state_of_registration": state_dropdown,
            "unladen_weight":        "80000",

            # Insurance Details
            "insurance_company":     d["insurance"]["company"],
            "insurance_eff_date":    iso_to_portal_date(d["insurance"]["effectiveDate"]),
            "insurance_exp_date":    iso_to_portal_date(d["insurance"]["expirationDate"]),
            "policy_no":             d["insurance"]["policyNumber"],

            # Operator Details
            "operator_usdot":        d["usdot"],

            # Metadata (not sent to portal, used for logging/results)
            "_permitId":             permit["permitId"],
            "_driverName":           f"{d['firstName']} {d['lastName']}",
            "_tractor":              d.get("tractor", ""),
            "_portalPermitType":     portal_permit_type,
        })

    return results
