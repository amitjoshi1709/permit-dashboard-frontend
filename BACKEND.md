# Mega Trucking — Backend System Prompt

You are building the backend API server for the Mega Trucking Permit Dashboard. This server sits between a React frontend and Playwright automation scripts that fill permit forms on state portals.

---

## Architecture

```
┌──────────────┐        ┌──────────────────┐        ┌──────────────────────┐
│   Dashboard   │───────▶│   Backend API     │───────▶│  Automation Server   │
│  (React app)  │  HTTP  │  (port 3001)      │  HTTP  │  (Playwright scripts)│
│  localhost:5173│◀──────│                   │◀──────│  fills portal forms  │
└──────────────┘        └──────────────────┘        └──────────────────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │    Supabase      │
                     │  (PostgreSQL)    │
                     │  `fleet` table   │
                     └──────────────────┘
```

**Flow:**
1. Dispatcher selects driver(s), state(s), permit type, and effective date on the dashboard
2. Dashboard sends only tractor numbers + state codes + permit type + effective date to the backend
3. Backend looks up full driver/vehicle/insurance details from Supabase `fleet` table
4. Backend forwards the complete payload to the automation server via HTTP
5. Playwright scripts use that payload to fill state portal forms — **automation stops before payment**
6. Automation server reports results back; backend updates permit status

---

## Supabase Database

### Table: `fleet`

This is the single source of truth for all driver and vehicle data. Column names contain spaces and special characters — **always use double quotes in SQL**.

```sql
CREATE TABLE fleet (
  id                          SERIAL PRIMARY KEY,
  "Tractor Number"            TEXT UNIQUE NOT NULL,
  "Driver Type"               TEXT NOT NULL,
  "Year"                      INTEGER,
  "Make"                      TEXT,
  "VIN (Serial Number)"       TEXT,
  "Tag #"                     TEXT,
  "Tag State"                 TEXT,
  "First Name"                TEXT NOT NULL,
  "Last Name"                 TEXT NOT NULL,
  "Driver Code"               TEXT,
  "USDOT"                     TEXT,
  "FEIN"                      TEXT,
  "Insurance Company"         TEXT,
  "Insurance Effective Date"  TEXT,
  "Insurance Expiration Date" TEXT,
  "Insurance Policy Number"   TEXT,
  active                      BOOLEAN DEFAULT TRUE,
  created_at                  TIMESTAMPTZ DEFAULT NOW()
);
```

**Example query:**
```sql
SELECT "Tractor Number", "First Name", "Last Name", "Driver Type", "VIN (Serial Number)", "USDOT"
FROM fleet
WHERE active = true;
```

### Driver Type Logic

| Type        | Category       | USDOT        | FEIN     | Insurance                          |
|-------------|---------------|--------------|----------|------------------------------------|
| F, LP, T    | Mega trucks   | `2582238`    | N/A      | Prime Property and Casualty, PC24040671, 04/11/2025–04/11/2026 |
| OT, BC, AC, WC | Owner-operators | Driver's own | Driver's own | Driver's own — stored in fleet table |

- **F/LP/T drivers**: USDOT is always `2582238`. Insurance is always Mega's policy. FEIN is blank.
- **OT/BC/AC/WC drivers**: All fields come from the `fleet` table as entered by the dispatcher.

---

## Dashboard → Backend API Contract

The dashboard frontend (`src/api.js`) makes these HTTP calls. When the real backend is ready, only the `USE_MOCK` flag needs to flip.

### `GET /api/drivers`

Returns active drivers for the dispatcher search. The dashboard displays name, tractor, and type. It also uses the full detail set for the Driver Database editor.

**Response `200`**
```json
[
  {
    "id": 1,
    "firstName": "Jonattan",
    "lastName": "Vazquez Perez",
    "name": "Jonattan Vazquez Perez",
    "tractor": "F894",
    "driverType": "F",
    "year": 2016,
    "make": "Freightliner",
    "vin": "3HSDJAPRXGN030818",
    "tagNumber": "FL-1234",
    "tagState": "FL",
    "usdot": "2582238",
    "fein": "",
    "insuranceCompany": "Prime Property and Casualty",
    "insuranceEffective": "04/11/2025",
    "insuranceExpiration": "04/11/2026",
    "policyNumber": "PC24040671"
  }
]
```

**Source query:**
```sql
SELECT * FROM fleet WHERE active = true ORDER BY "Last Name", "First Name";
```

Map column names to camelCase response fields:
| Supabase Column               | JSON Field           |
|-------------------------------|----------------------|
| `id`                          | `id`                 |
| `"First Name"`                | `firstName`          |
| `"Last Name"`                 | `lastName`           |
| (computed)                    | `name` = `firstName + " " + lastName` |
| `"Tractor Number"`           | `tractor`            |
| `"Driver Type"`              | `driverType`         |
| `"Year"`                     | `year`               |
| `"Make"`                     | `make`               |
| `"VIN (Serial Number)"`      | `vin`                |
| `"Tag #"`                    | `tagNumber`          |
| `"Tag State"`                | `tagState`           |
| `"USDOT"`                    | `usdot`              |
| `"FEIN"`                     | `fein`               |
| `"Insurance Company"`        | `insuranceCompany`   |
| `"Insurance Effective Date"` | `insuranceEffective` |
| `"Insurance Expiration Date"`| `insuranceExpiration` |
| `"Insurance Policy Number"`  | `policyNumber`       |

---

### `POST /api/drivers`

Creates a new driver in the `fleet` table. Called from the Driver Database editor.

**Request body** — same shape as the driver object above (without `id`, `name`).

**Response `200`** — the created driver with `id` assigned.

---

### `PUT /api/drivers/:id`

Updates an existing driver. Accepts a partial object with only the fields being changed.

**Response `200`** — the updated driver object.

---

### `DELETE /api/drivers/:id`

Soft-deletes a driver by setting `active = false`. Do NOT hard-delete — permit history references these drivers.

**Response `200`**
```json
{ "success": true }
```

---

### `POST /api/permits/order`

The dashboard sends the minimal info needed. The backend resolves everything else from Supabase.

**Request body**
```json
{
  "driverIds":     [1, 3],
  "states":        ["GA"],
  "permitType":    "trip_fuel",
  "effectiveDate": "2026-03-24"
}
```

**`permitType` values:**
| Value        | Label         |
|------------- |---------------|
| `trip_fuel`  | Trip and Fuel |
| `os_ow`     | OS/OW         |
| `trip`       | Trip          |
| `fuel`       | Fuel          |

**`effectiveDate`**: ISO date string (`YYYY-MM-DD`). Defaults to today on the frontend.

**What the backend must do:**

1. Validate `driverIds` exist in `fleet` and are `active = true`
2. Validate `states` are in the supported list
3. Validate `permitType` is one of the allowed values
4. For each driver × state combination:
   - Query the full driver record from `fleet`
   - Build the automation payload (see below)
5. Send HTTP request to the automation server with the enriched payload
6. Create permit records in `Pending` status
7. Return immediately — do not wait for automation

**Response `200`**
```json
{
  "jobId":   "JOB-1234",
  "queued":  2,
  "message": "Permits queued. Automation will stop before payment."
}
```

**Error responses**
```json
{ "error": "No valid driver IDs provided" }        // 400
{ "error": "State XX is not currently supported" }  // 400
{ "error": "Invalid permit type" }                  // 400
{ "error": "Failed to queue permits" }              // 500
```

---

### `GET /api/permits/history`

Returns all permit records for the history table.

**Response `200`**
```json
[
  {
    "id": "P0046",
    "driverName": "Lopez, M.",
    "tractor": "F712",
    "state": "GA",
    "type": "ITP",
    "status": "Active",
    "effDate": "03/01/2026",
    "expDate": "03/08/2026",
    "fee": 30
  }
]
```

| Field        | Type   | Values / Format                            |
|------------- |--------|--------------------------------------------|
| `id`         | string | Unique permit ID (e.g. `P0046`)            |
| `driverName` | string | `"Last, F."` format                        |
| `tractor`    | string | Tractor/unit number                        |
| `state`      | string | Two-letter state code                      |
| `type`       | string | `"ITP"` or `"MFTP"`                        |
| `status`     | string | `"Active"`, `"Expired"`, or `"Pending"`    |
| `effDate`    | string | `MM/DD/YYYY`                               |
| `expDate`    | string | `MM/DD/YYYY`                               |
| `fee`        | number | Dollar amount, `0` if pending              |

- Return newest first (descending by effective date)
- Frontend filters by `status` and `type` client-side

---

### `GET /api/permits/blankets`

Returns blanket permits on file.

**Response `200`**
```json
[
  {
    "id": "BL001",
    "driverId": 1,
    "driverName": "Jonattan Vazquez Perez",
    "state": "FL",
    "num": "BP-FL-2026-001",
    "exp": "12/31/2026"
  }
]
```

---

### `POST /api/permits/callback`

Receives results from the automation server after a Playwright script completes.

**Request body**
```json
{
  "permitId": "P0051",
  "jobId": "JOB-1234",
  "status": "Active",
  "fee": 30.00,
  "type": "ITP",
  "portalConfirmation": "...",
  "pdfUrl": "..."
}
```

**Backend action:**
1. Update the permit record: `Pending` → `Active` or `Expired` (if failed)
2. Store fee, type, confirmation number, PDF URL

---

## Automation Server Payload

When the backend receives `POST /api/permits/order`, it builds this payload from the `fleet` table and sends it to the automation server. This is what the Playwright scripts use to fill portal forms.

```json
POST {AUTOMATION_SERVER_URL}/run

{
  "jobId": "JOB-1234",
  "permits": [
    {
      "permitId": "P0051",
      "state": "GA",
      "permitType": "trip_fuel",
      "effectiveDate": "2026-03-24",
      "driver": {
        "firstName": "Jonattan",
        "lastName": "Vazquez Perez",
        "driverType": "F",
        "driverCode": "JVAZQUE",
        "tractor": "F894",
        "year": 2016,
        "make": "Freightliner",
        "vin": "3HSDJAPRXGN030818",
        "tagNumber": "FL-1234",
        "tagState": "FL",
        "usdot": "2582238",
        "fein": "",
        "insurance": {
          "company": "Prime Property and Casualty",
          "effectiveDate": "04/11/2025",
          "expirationDate": "04/11/2026",
          "policyNumber": "PC24040671"
        }
      }
    }
  ],
  "callbackUrl": "{BACKEND_URL}/api/permits/callback"
}
```

**Key points:**
- Every field the Playwright script needs is in this payload — the script should not need to query any database
- `effectiveDate` comes from the dashboard (user-selected, defaults to today)
- All other fields come from the `fleet` table in Supabase
- `driverCode` is the `"Driver Code"` column — used by some portals as an identifier
- The `insurance` object is nested for clarity
- Include `callbackUrl` so the automation server can POST results back

---

## Supported States

All states are selectable on the dashboard (no "coming soon" restrictions). The backend should accept any of these:

```
GA, FL, SC, NC, TN, AL, MS, LA, TX
```

---

## CORS

The frontend runs on `localhost:5173` (Vite dev). The backend must set:

```
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type
```

Restrict the origin to the production domain in deployment.

---

## Environment Variables

```
PORT=3001
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
AUTOMATION_SERVER_URL=http://automation-host:PORT
CALLBACK_BASE_URL=http://backend-host:3001
```

Use the Supabase JS client (`@supabase/supabase-js`) with the service role key for backend access. Never expose the service key to the frontend.

---

## Checklist

- [ ] `GET /api/drivers` — query `fleet` where `active = true`, map columns to camelCase
- [ ] `POST /api/drivers` — insert into `fleet`, return created record
- [ ] `PUT /api/drivers/:id` — update `fleet` row
- [ ] `DELETE /api/drivers/:id` — set `active = false` (soft delete)
- [ ] `POST /api/permits/order` — validate input, query `fleet` for full details, build automation payload, forward to automation server
- [ ] `GET /api/permits/history` — return permits with `effDate`/`expDate`, status `Active`/`Expired`/`Pending`
- [ ] `GET /api/permits/blankets` — return blanket permits
- [ ] `POST /api/permits/callback` — receive automation results, update permit records
- [ ] CORS configured for dashboard origin
- [ ] Supabase client initialized with service role key
- [ ] Column name mapping handles double-quoted Supabase columns
- [ ] Soft delete only — never hard-delete drivers
- [ ] Automation payload includes every field Playwright scripts need
- [ ] Permit records created in `Pending` status, updated on callback
