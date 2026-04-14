import os
from supabase import create_client, Client
from dotenv import load_dotenv

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
            "driverName": p.get("driver_name", ""),
            "tractor": p.get("tractor", ""),
            "state": p.get("state", ""),
            "type": p.get("type") or p.get("permit_type", ""),
            "status": p.get("status", ""),
            "effDate": p.get("eff_date", ""),
            "expDate": p.get("exp_date", ""),
            "fee": p.get("fee", 0),
        }
        for p in result.data
    ]
