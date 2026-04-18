"""
Company-level constants used by automation scripts.

These values don't change per driver — they're Mega Trucking's fixed details
for portal form fields like legal name, mailing address, and contact email.
"""

COMPANY = {
    "legal_name": "Mega Trucking LLC",
    "dba": "Mega Trucking LLC",
    "primary_email": "MICHAEL@MEGATRUCKINGLLC.COM",
    "confirm_email": "MICHAEL@MEGATRUCKINGLLC.COM",
    "street": "5979 NW 151ST ST",
    "unit_type": "SUITE",
    "unit": "101",
    "city": "Miami Lakes",
    "state": "FL",
    "zip": "33014",
    "county": "MIAMI-DADE",
    "country": "USA",
    "phone": "786-332-5691",
}

# Company driver defaults (F, LP, T types)
COMPANY_DRIVER_DEFAULTS = {
    "usdot": "2582238",
    "insurance_company": "Prime Property and Casualty",
    "insurance_effective": "04/11/2025",
    "insurance_expiration": "04/11/2026",
    "policy_number": "PC24040671",
}

COMPANY_TYPES = {"F", "LP", "T"}

SUPPORTED_STATES = {"GA", "FL", "SC", "NC", "TN", "AL", "MS", "LA", "TX", "AR", "AR"}
VALID_PERMIT_TYPES = {
    "trip_fuel", "os_ow", "trip", "fuel",
    # Florida-only blanket variants
    "fl_blanket_bulk", "fl_blanket_inner_bridge", "fl_blanket_flatbed",
    # Alabama-only
    "al_annual_osow",
}

# Georgia portal config
# Credentials come from env vars: GA_PORTAL_USERNAME, GA_PORTAL_PASSWORD
GA_ACCOUNT_NO = "82761"
