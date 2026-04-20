import os
from datetime import datetime, timezone
from supabase import create_client, Client
from dotenv import load_dotenv
from encryption import encrypt_card, decrypt_card

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Column mapping: Supabase → camelCase ─────────────────────────────

COLUMN_MAP = {
    "id": "id",
    "Tractor Number": "tractor",
    "Driver Type": "driverType",
    "Year": "year",
    "Make": "make",
    "model": "model",
    "VIN (Serial Number)": "vin",
    "Tag #": "tagNumber",
    "Tag State": "tagState",
    "First Name": "firstName",
    "Last Name": "lastName",
    "Driver Code": "driverCode",
    "USDOT": "usdot",
    "FEIN": "fein",
    "Insurance Company": "insuranceCompany",
    "Insurance Effective Date": "insuranceEffective",
    "Insurance Expiration Date": "insuranceExpiration",
    "Insurance Policy Number": "policyNumber",
}

# Reverse: camelCase → Supabase column name
REVERSE_MAP = {v: k for k, v in COLUMN_MAP.items()}


def row_to_driver(row: dict) -> dict:
    """Convert a Supabase fleet row to the camelCase driver object the frontend expects."""
    driver = {}
    for db_col, json_key in COLUMN_MAP.items():
        if db_col in row:
            driver[json_key] = row[db_col]
    driver["name"] = f"{driver.get('firstName', '')} {driver.get('lastName', '')}".strip()
    return driver


def driver_to_row(data: dict) -> dict:
    """Convert camelCase driver fields to Supabase column names for insert/update."""
    row = {}
    for json_key, value in data.items():
        if json_key in REVERSE_MAP:
            row[REVERSE_MAP[json_key]] = value
    return row


# ── Query functions ──────────────────────────────────────────────────

def get_active_drivers() -> list[dict]:
    result = (
        supabase.table("fleet")
        .select("*")
        .eq("active", True)
        .order("Last Name")
        .order("First Name")
        .execute()
    )
    return [row_to_driver(r) for r in result.data]


def get_driver_by_id(driver_id: int) -> dict | None:
    result = (
        supabase.table("fleet")
        .select("*")
        .eq("id", driver_id)
        .eq("active", True)
        .single()
        .execute()
    )
    return row_to_driver(result.data) if result.data else None


def get_drivers_by_ids(driver_ids: list[int]) -> list[dict]:
    result = (
        supabase.table("fleet")
        .select("*")
        .in_("id", driver_ids)
        .eq("active", True)
        .execute()
    )
    return [row_to_driver(r) for r in result.data]


def create_driver_record(data: dict) -> dict:
    row = driver_to_row(data)
    result = supabase.table("fleet").insert(row).execute()
    return row_to_driver(result.data[0])


def update_driver_record(driver_id: int, data: dict) -> dict:
    row = driver_to_row(data)
    result = (
        supabase.table("fleet")
        .update(row)
        .eq("id", driver_id)
        .execute()
    )
    return row_to_driver(result.data[0])


def soft_delete_driver(driver_id: int) -> bool:
    result = (
        supabase.table("fleet")
        .update({"active": False})
        .eq("id", driver_id)
        .execute()
    )
    return len(result.data) > 0


def _normalize_date_for_supabase(value: str) -> str:
    """Convert MM/DD/YYYY → YYYY-MM-DD. Passes through if already ISO or blank."""
    if not value:
        return value
    v = value.strip()
    # Already ISO (YYYY-MM-DD)
    if len(v) == 10 and v[4] == "-" and v[7] == "-":
        return v
    # MM/DD/YYYY → YYYY-MM-DD
    if "/" in v:
        parts = v.split("/")
        if len(parts) == 3:
            m, d, y = parts
            return f"{y.zfill(4)}-{m.zfill(2)}-{d.zfill(2)}"
    return v


def update_mega_insurance(insurance: dict) -> int:
    """
    Update insurance fields on every Mega driver (driverType in F, LP, T).
    Returns the number of rows updated.

    `insurance` dict uses camelCase keys — same shape as the driver object:
      insuranceCompany, insuranceEffective, insuranceExpiration, policyNumber
    """
    # Drop empty strings/None so we don't try to write "" into date columns
    cleaned = {k: v for k, v in insurance.items() if v not in (None, "")}
    # Normalize dates to ISO for PostgreSQL date columns
    if "insuranceEffective" in cleaned:
        cleaned["insuranceEffective"] = _normalize_date_for_supabase(cleaned["insuranceEffective"])
    if "insuranceExpiration" in cleaned:
        cleaned["insuranceExpiration"] = _normalize_date_for_supabase(cleaned["insuranceExpiration"])
    row = driver_to_row(cleaned)
    if not row:
        return 0
    result = (
        supabase.table("fleet")
        .update(row)
        .in_("Driver Type", ["F", "LP", "T"])
        .execute()
    )
    return len(result.data)


def _iso_to_mmddyyyy(value: str) -> str:
    """Convert YYYY-MM-DD → MM/DD/YYYY for display. Passes through otherwise."""
    if not value:
        return value
    v = str(value).strip()
    if len(v) == 10 and v[4] == "-" and v[7] == "-":
        y, m, d = v.split("-")
        return f"{m}/{d}/{y}"
    return v


def get_mega_insurance() -> dict:
    """Fetch the current Mega insurance (reads from any F/LP/T row)."""
    # Supabase strips spaces inside the select string for aliasing, which
    # breaks our column names. Select * and extract the fields in Python.
    result = (
        supabase.table("fleet")
        .select("*")
        .in_("Driver Type", ["F", "LP", "T"])
        .limit(1)
        .execute()
    )
    if not result.data:
        return {
            "insuranceCompany": "",
            "insuranceEffective": "",
            "insuranceExpiration": "",
            "policyNumber": "",
        }
    row = result.data[0]
    return {
        "insuranceCompany": row.get("Insurance Company", "") or "",
        "insuranceEffective": _iso_to_mmddyyyy(row.get("Insurance Effective Date", "") or ""),
        "insuranceExpiration": _iso_to_mmddyyyy(row.get("Insurance Expiration Date", "") or ""),
        "policyNumber": row.get("Insurance Policy Number", "") or "",
    }


# ── Permit functions ─────────────────────────────────────────────────

def generate_permit_ids(count: int) -> list[str]:
    """Generate `count` sequential permit IDs in P0001 format."""
    result = (
        supabase.table("permits")
        .select("id")
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    next_num = 1
    if result.data:
        last_id = result.data[0]["id"]
        last_num = int(last_id.replace("P", ""))
        next_num = last_num + 1
    return [f"P{str(next_num + i).zfill(4)}" for i in range(count)]


def insert_permits(rows: list[dict]):
    """Insert permit rows into the permits table."""
    if not rows:
        return
    supabase.table("permits").insert(rows).execute()


def update_permit_status(permit_id: str, status: str, fee: float = None):
    """Update a permit's status (and optionally fee) after automation runs."""
    update_data = {"status": status}
    if fee is not None:
        update_data["fee"] = fee
    supabase.table("permits").update(update_data).eq("id", permit_id).execute()


def get_permit_history() -> list[dict]:
    """Fetch all permits ordered by most recent first."""
    result = (
        supabase.table("permits")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return [
        {
            "id": p["id"],
            "driverId": p.get("driver_id"),
            "driverName": p.get("driver_name", ""),
            "tractor": p.get("tractor", ""),
            "state": p.get("state", ""),
            "type": p.get("type") or p.get("permit_type", ""),
            "status": p.get("status", ""),
            "effDate": p.get("eff_date", ""),
            "expDate": p.get("exp_date", ""),
            "fee": p.get("fee", 0),
            # JSONB column — contains the original POST extraFields payload (dimensions,
            # axles, etc.) for FL/OS-OW permits. Null for simple trip/fuel permits.
            "extraFields": p.get("extra_fields"),
        }
        for p in result.data
    ]


# ── Payment card (encrypted) ───────────────────────────────────────

def _detect_brand(card_number: str) -> str:
    n = card_number.replace(" ", "")
    if n.startswith("4"):
        return "VISA"
    if n[:2] in ("51", "52", "53", "54", "55"):
        return "MC"
    if n[:2] in ("34", "37"):
        return "AMEX"
    if n.startswith("6011") or n.startswith("65"):
        return "DISC"
    return "CARD"


def get_payment_card() -> dict:
    """Fetch encrypted card from settings table, return MASKED version for the frontend."""
    result = (
        supabase.table("settings")
        .select("value")
        .eq("key", "payment_card")
        .single()
        .execute()
    )
    if not result.data or not result.data.get("value"):
        return {"hasCard": False}

    card = decrypt_card(result.data["value"])
    digits = card.get("cardNumber", "").replace(" ", "")
    last4 = digits[-4:] if len(digits) >= 4 else ""

    return {
        "hasCard": True,
        "lastFour": last4,
        "brand": _detect_brand(digits),
        "cardholderName": card.get("cardholderName", ""),
        "expMonth": card.get("expMonth", ""),
        "expYear": card.get("expYear", ""),
        "billingStreet": card.get("billingStreet", ""),
        "billingCity": card.get("billingCity", ""),
        "billingState": card.get("billingState", ""),
        "billingZip": card.get("billingZip", ""),
    }


def save_payment_card(card_data: dict) -> bool:
    """Encrypt card data and upsert into the settings table."""
    ciphertext = encrypt_card(card_data)
    supabase.table("settings").upsert({
        "key": "payment_card",
        "value": ciphertext,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    return True


def get_decrypted_payment_card() -> dict:
    """Fetch and decrypt the FULL card for automation scripts. Never call from API endpoints."""
    result = (
        supabase.table("settings")
        .select("value")
        .eq("key", "payment_card")
        .single()
        .execute()
    )
    if not result.data or not result.data.get("value"):
        return {}
    return decrypt_card(result.data["value"])
