# Permit Dashboard — Backend Spec

## Overview

The dashboard frontend is complete and currently runs against mock data. The backend is an HTTP server (port `3001`) that:

1. Serves driver/permit data from a database
2. Accepts permit order requests from the dashboard
3. Forwards those orders via HTTP to a **separate automation server** that runs the actual browser scripts against state portals
4. Tracks permit status and stores results

The frontend lives in `src/api.js`. When the backend is ready, flip `USE_MOCK` to `false` — no other frontend changes needed.

---

## Architecture

```
┌──────────────┐       ┌──────────────────┐       ┌──────────────────────┐
│   Dashboard   │──────▶│   Backend API     │──────▶│  Automation Server   │
│  (React app)  │ HTTP  │  (port 3001)      │ HTTP  │  (separate host)     │
│               │◀──────│                   │◀──────│  runs portal scripts │
└──────────────┘       └──────────────────┘       └──────────────────────┘
```

- **Dashboard → Backend**: REST calls defined below
- **Backend → Automation Server**: Backend makes HTTP requests to trigger automation scripts and poll for results
- **Automation stops before payment** — the scripts fill forms but do NOT complete checkout

---

## API Endpoints

### `GET /api/drivers`

Returns the list of drivers the dispatcher can select from. The dashboard only needs `id`, `name`, and `tractor` — do not expose sensitive fields (SSN, license, insurance, etc.).

**Response `200`**
```json
[
  { "id": "D001", "name": "Jonattan Vazquez Perez", "tractor": "F894"  },
  { "id": "D002", "name": "Maria Gonzalez",         "tractor": "F712"  },
  { "id": "D003", "name": "Carlos Reyes",           "tractor": "OT201" },
  { "id": "D004", "name": "Ana Torres",             "tractor": "BC102" }
]
```

Notes:
- Source this from your driver database/table
- The frontend searches by `name`, `tractor`, and `id` — all three must be present
- Keep the response flat and minimal

---

### `POST /api/permits/order`

The dashboard sends **only** driver IDs and state codes. The backend resolves everything else (VIN, USDOT, insurance, weight, carrier info, etc.) from its own database before forwarding to the automation server.

**Request body**
```json
{
  "driverIds":  ["D001", "D003"],
  "states":     ["GA"],
  "permitType": "trip_fuel"
}
```

**`permitType` values:**
| Value        | Label         |
|------------- |---------------|
| `trip_fuel`  | Trip and Fuel |
| `os_ow`     | OS/OW         |
| `trip`       | Trip          |
| `fuel`       | Fuel          |

**What the backend must do:**

1. Validate `driverIds` exist in the database
2. Validate `states` are supported and live
3. Validate `permitType` is one of the allowed values
3. For each driver × state combination, look up all required permit form fields from the database
4. Send an HTTP request to the automation server with the full payload (see Automation Server section below)
5. Create a job record and individual permit records in `pending` status
6. Return immediately — do not wait for automation to finish

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
// 400 — bad request
{ "error": "No valid driver IDs provided" }

// 400 — unsupported state
{ "error": "State XX is not currently supported" }

// 500 — internal
{ "error": "Failed to queue permits" }
```

---

### `GET /api/permits/history`

Returns all permit records for the history table. The frontend expects this exact shape.

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

**Field details:**

| Field        | Type   | Values / Format                            |
|------------- |--------|--------------------------------------------|
| `id`         | string | Unique permit ID (e.g. `P0046`)            |
| `driverName` | string | Display name, `"Last, F."` format          |
| `tractor`    | string | Tractor/unit number                        |
| `state`      | string | Two-letter state code (`GA`, `FL`, etc.)   |
| `type`       | string | `"ITP"` or `"MFTP"`                        |
| `status`     | string | `"Active"`, `"Expired"`, or `"Pending"`    |
| `effDate`    | string | Effective date `MM/DD/YYYY`                |
| `expDate`    | string | Expiration date `MM/DD/YYYY`               |
| `fee`        | number | Dollar amount, `0` if pending              |

Notes:
- Return newest first (descending by effective date)
- The frontend filters by `status` and `type` client-side, so return all records
- Consider pagination later if the table grows large

---

### `GET /api/permits/blankets`

Returns all blanket permits on file. Used by the dashboard and blanket permits view.

**Response `200`**
```json
[
  {
    "id": "BL001",
    "driverId": "D001",
    "driverName": "Jonattan Vazquez Perez",
    "state": "FL",
    "num": "BP-FL-2026-001",
    "exp": "12/31/2026"
  }
]
```

| Field        | Type   | Description                              |
|------------- |--------|------------------------------------------|
| `id`         | string | Unique blanket permit ID                 |
| `driverId`   | string | References a driver                      |
| `driverName` | string | Full driver name for display             |
| `state`      | string | Two-letter state code                    |
| `num`        | string | Blanket permit number                    |
| `exp`        | string | Expiration date `MM/DD/YYYY`             |

---

## Automation Server Integration

The automation server is a **separate service** that runs browser automation scripts against state permit portals. The backend communicates with it over HTTP.

### Triggering automation

When the backend receives a `POST /api/permits/order`, it should forward the full permit data to the automation server:

```
POST {AUTOMATION_SERVER_URL}/run
Content-Type: application/json

{
  "jobId": "JOB-1234",
  "permits": [
    {
      "permitId": "P-1515487",
      "state": "GA",
      "driver": {
        "id": "D001",
        "name": "Jonattan Vazquez Perez",
        "tractor": "F894",
        "vin": "...",
        "usdot": "...",
        "insurance": { ... },
        "weight": ...,
        "driverType": "...",
        "carrier": { ... }
      }
    }
  ],
  "callbackUrl": "{BACKEND_URL}/api/permits/callback"
}
```

Key points:
- The backend enriches the payload with all permit form fields from its database — the dashboard never has this data
- Include a `callbackUrl` so the automation server can notify the backend when each permit completes
- Each permit in the array is one driver × state combination

### Receiving results (callback)

The automation server should call back to the backend when a permit finishes (success or failure):

```
POST {BACKEND_URL}/api/permits/callback
Content-Type: application/json

{
  "permitId": "P-1515487",
  "jobId": "JOB-1234",
  "status": "issued",
  "fee": 31.00,
  "type": "ITP",
  "portalConfirmation": "...",
  "pdfUrl": "..."
}
```

On receiving this callback, the backend should:
1. Update the permit record status (`pending` → `issued` or `failed`)
2. Store the fee, type, and any portal confirmation details
3. Store the PDF URL if the automation captured the permit document

### Alternative: Polling

If callbacks aren't feasible, the backend can poll the automation server:

```
GET {AUTOMATION_SERVER_URL}/status/{jobId}
```

Response:
```json
{
  "jobId": "JOB-1234",
  "permits": [
    { "permitId": "P-1515487", "status": "issued", "fee": 31.00, "type": "ITP" },
    { "permitId": "P-1515488", "status": "pending" }
  ]
}
```

Poll on an interval (e.g., every 10–15 seconds) until all permits are no longer `pending`.

---

## Data Ownership Boundary

This is critical — the dashboard and backend have a clear data boundary:

| Data                              | Who owns it          |
|-----------------------------------|----------------------|
| Driver IDs, state codes           | Dashboard sends these |
| VIN, USDOT, insurance, weight, carrier info, driver type | Backend database only |
| Permit form field mapping per state | Backend / automation  |
| Permit results (status, fee, PDF) | Backend stores from automation |

The dashboard **never** sees, stores, or transmits sensitive permit form data. It only sends driver IDs and state codes. The backend resolves everything else.

---

## CORS

The frontend runs on `localhost:5173` (Vite dev server) and calls `localhost:3001`. The backend must set CORS headers:

```
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type
```

In production, restrict the origin to the actual dashboard domain.

---

## Environment Variables (suggested)

```
PORT=3001
DATABASE_URL=...
AUTOMATION_SERVER_URL=http://automation-host:PORT
CALLBACK_BASE_URL=http://backend-host:3001
```

---

## Checklist

- [ ] `GET /api/drivers` — returns driver list (id, name, tractor only)
- [ ] `POST /api/permits/order` — validates input (including `permitType`), enriches from DB, forwards to automation server, returns job ID
- [ ] `GET /api/permits/history` — returns all permits with `effDate`/`expDate` and status `Active`/`Expired`/`Pending`
- [ ] `GET /api/permits/blankets` — returns blanket permits on file
- [ ] `POST /api/permits/callback` — receives automation results, updates permit records
- [ ] CORS configured for dashboard origin
- [ ] Automation payloads include all form fields the portal scripts need
- [ ] Permit records created in `Pending` status on order, updated on callback
- [ ] Sensitive data (VIN, USDOT, insurance) never sent to the dashboard
