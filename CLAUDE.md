# Permit Dashboard — Claude Code Spec

## Project

Dispatcher-facing web dashboard for Mega Trucking LLC to order trip and fuel permits across state portals. Frontend only — designed to wire up to a backend HTTP server later.

---

## Stack

- **React + Vite** (JS)
- **Tailwind CSS** for styling
- State management: React `useState` / `useContext` — no Redux
- HTTP: native `fetch` isolated in a single `api.js` module (all backend calls go through here, making the mock → real swap trivial)

---

## Data Ownership — Critical

The dashboard collects **only two things** from the dispatcher:

1. **Driver(s)** — selected from a list fetched from the backend
2. **State(s)** — selected from a hardcoded list of supported portals


Everything else required to fill a permit form (VIN, tractor number, USDOT, insurance info, weight, driver type, carrier details, etc.) is the backend's responsibility. The dashboard never holds, displays, or sends that data — it only sends driver IDs and state codes.

---

## File Structure

```
src/
  api.js          ← all fetch calls + mock data
  App.jsx
  components/
    Header.jsx
    StatCards.jsx
    OrderForm.jsx
    HistoryTable.jsx
    Badge.jsx
    LogConsole.jsx
```

---

## Backend Contract (mock now, real later)

All API calls live in `src/api.js`. Mocks return hardcoded data with a short `setTimeout`. When the real server is ready, only this file changes.

```js
const API_BASE = "http://localhost:3001"; // change for production

export async function fetchDrivers()       { /* GET  /api/drivers        */ }
export async function submitPermitOrder(p) { /* POST /api/permits/order  */ }
export async function fetchPermitHistory() { /* GET  /api/permits/history */ }
```

### GET `/api/drivers` — mock response
Returns only what the UI needs to render the driver list. Nothing more.
```json
[
  { "id": "D001", "name": "Jonattan Vazquez Perez", "tractor": "F894"  },
  { "id": "D002", "name": "Maria Gonzalez",         "tractor": "F712"  },
  { "id": "D003", "name": "Carlos Reyes",           "tractor": "OT201" },
  { "id": "D004", "name": "Ana Torres",             "tractor": "BC102" }
]
```

### POST `/api/permits/order` — payload (what the dashboard sends)
```json
{
  "driverIds": ["D001", "D003"],
  "states":    ["GA"]
}
```
That's it. The backend resolves all permit form fields from its own database.

### POST `/api/permits/order` — response
```json
{
  "jobId":   "JOB-1234",
  "queued":  2,
  "message": "Permits queued. Automation will stop before payment."
}
```

### GET `/api/permits/history` — mock response
```json
[
  { "id": "P-1515486", "driverName": "Jonattan Vazquez Perez", "tractor": "F894",  "state": "GA", "type": "ITP",  "status": "issued", "date": "2026-01-28", "fee": 31.00 },
  { "id": "P-287178",  "driverName": "Maria Gonzalez",         "tractor": "F712",  "state": "GA", "type": "MFTP", "status": "issued", "date": "2026-01-22", "fee": 21.00 },
  { "id": "P-287102",  "driverName": "Carlos Reyes",           "tractor": "OT201", "state": "GA", "type": "ITP",  "status": "issued", "date": "2026-01-18", "fee": 31.00 },
  { "id": "P-286900",  "driverName": "Ana Torres",             "tractor": "BC102", "state": "GA", "type": "MFTP", "status": "failed",  "date": "2026-01-15", "fee": 0     }
]
```

---

## Supported States (hardcoded in UI)

```js
const STATES = [
  { code: "GA", label: "Georgia",        live: true  },
  { code: "LA", label: "Louisiana",      live: false },
  { code: "MS", label: "Mississippi",    live: false },
  { code: "AL", label: "Alabama",        live: false },
  { code: "FL", label: "Florida",        live: false },
  { code: "TX", label: "Texas",          live: false },
  { code: "TN", label: "Tennessee",      live: false },
  { code: "SC", label: "South Carolina", live: false },
];
```

Non-live states are visible but disabled with a "coming soon" indicator. Only live states can be selected.

---

## UI

### Theme
Dark industrial. Near-black background (`#0f1117`), amber accent (`#f0a500`), IBM Plex Sans + IBM Plex Mono. Dense, utilitarian — dispatcher tool, not a consumer app.

### Layout
```
┌─ Header (company name + live portal indicator) ────────┐
│  Stat cards: Total Issued · This Month · Total Fees     │
├─ Tabs: [Order Permits] [Permit History] ────────────────┤
│  Tab content                                            │
└─────────────────────────────────────────────────────────┘
```

### Order Form (two-column)

**Left column**
- State selector — toggle buttons, only live states clickable
- Payment boundary notice — static callout: "Automation stops before payment. You will complete checkout manually."

**Right column**
- Driver checklist — loaded from `GET /api/drivers`, each row shows name + tractor #
- Submit button: `"Queue N permit(s) → GA"` — disabled until ≥1 driver and ≥1 state selected
- Log console — appears after submit, timestamped monospace messages

### Permit History
- Filter pills: All · Issued · Failed · Pending
- Table columns: Permit # · Driver · Tractor · State · Type · Date · Fee · Status · PDF
- Refresh button top-right

### Badges
Colored pills: `ITP` (blue) · `MFTP` (amber) · `issued` (green) · `failed` (red) · `pending` (amber)

---

## Dev Setup

```bash
npm create vite@latest permit-dashboard -- --template react
cd permit-dashboard
npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
npm run dev
```