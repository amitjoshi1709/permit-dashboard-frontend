const API_BASE = "http://localhost:3001";
const USE_MOCK = true;

// ── Supported states ──────────────────────────────────────────────────
export const STATES = [
  { code: "GA", label: "Georgia" },
  { code: "FL", label: "Florida" },
  { code: "SC", label: "South Carolina" },
  { code: "NC", label: "North Carolina" },
  { code: "TN", label: "Tennessee" },
  { code: "AL", label: "Alabama" },
  { code: "MS", label: "Mississippi" },
  { code: "LA", label: "Louisiana" },
  { code: "TX", label: "Texas" },
];

// ── Permit types ──────────────────────────────────────────────────────
export const PERMIT_TYPES = [
  { value: "trip_fuel", label: "Trip and Fuel" },
  { value: "os_ow", label: "OS/OW" },
  { value: "trip", label: "Trip" },
  { value: "fuel", label: "Fuel" },
];

// ── Mock data ─────────────────────────────────────────────────────────
const MOCK_DRIVERS = [
  { id: "D001", name: "Jonattan Vazquez Perez", tractor: "F894" },
  { id: "D002", name: "Mario Lopez", tractor: "F712" },
  { id: "D003", name: "Roberto Campos", tractor: "T211" },
  { id: "D004", name: "Pedro Gomez", tractor: "T305" },
];

const MOCK_BLANKETS = [
  { id: "BL001", driverId: "D001", driverName: "Jonattan Vazquez Perez", state: "FL", num: "BP-FL-2026-001", exp: "12/31/2026" },
  { id: "BL002", driverId: "D002", driverName: "Mario Lopez", state: "FL", num: "BP-FL-2026-002", exp: "12/31/2026" },
  { id: "BL003", driverId: "D004", driverName: "Pedro Gomez", state: "GA", num: "BP-GA-2026-001", exp: "06/30/2026" },
  { id: "BL004", driverId: "D001", driverName: "Jonattan Vazquez Perez", state: "SC", num: "BP-SC-2026-001", exp: "03/31/2026" },
  { id: "BL005", driverId: "D003", driverName: "Roberto Campos", state: "NC", num: "BP-NC-2026-001", exp: "09/30/2026" },
  { id: "BL006", driverId: "D002", driverName: "Mario Lopez", state: "TN", num: "BP-TN-2026-001", exp: "07/15/2026" },
];

const MOCK_HISTORY = [
  { id: "P0041", driverName: "Vazquez Perez, J.", tractor: "F894", state: "GA", type: "ITP", status: "Expired", effDate: "01/15/2026", expDate: "01/22/2026", fee: 30 },
  { id: "P0042", driverName: "Lopez, M.", tractor: "F712", state: "GA", type: "MFTP", status: "Expired", effDate: "01/22/2026", expDate: "01/31/2026", fee: 25 },
  { id: "P0043", driverName: "Campos, R.", tractor: "T211", state: "GA", type: "ITP", status: "Expired", effDate: "02/01/2026", expDate: "02/08/2026", fee: 30 },
  { id: "P0044", driverName: "Gomez, P.", tractor: "T305", state: "GA", type: "MFTP", status: "Expired", effDate: "02/10/2026", expDate: "02/28/2026", fee: 25 },
  { id: "P0045", driverName: "Vazquez Perez, J.", tractor: "F894", state: "GA", type: "ITP", status: "Expired", effDate: "02/20/2026", expDate: "02/27/2026", fee: 30 },
  { id: "P0046", driverName: "Lopez, M.", tractor: "F712", state: "GA", type: "ITP", status: "Active", effDate: "03/01/2026", expDate: "03/08/2026", fee: 30 },
  { id: "P0047", driverName: "Campos, R.", tractor: "T211", state: "GA", type: "MFTP", status: "Active", effDate: "03/05/2026", expDate: "03/15/2026", fee: 25 },
  { id: "P0048", driverName: "Gomez, P.", tractor: "T305", state: "GA", type: "ITP", status: "Active", effDate: "03/10/2026", expDate: "03/17/2026", fee: 30 },
  { id: "P0049", driverName: "Vazquez Perez, J.", tractor: "F894", state: "GA", type: "MFTP", status: "Active", effDate: "03/12/2026", expDate: "03/22/2026", fee: 25 },
  { id: "P0050", driverName: "Lopez, M.", tractor: "F712", state: "GA", type: "ITP", status: "Pending", effDate: "03/15/2026", expDate: "03/22/2026", fee: 30 },
];

// ── Helpers ────────────────────────────────────────────────────────────
function mock(data, delay = 400) {
  return new Promise((resolve) => setTimeout(() => resolve(data), delay));
}

// ── API functions ─────────────────────────────────────────────────────
export async function fetchDrivers() {
  if (USE_MOCK) return mock([...MOCK_DRIVERS], 300);
  const res = await fetch(`${API_BASE}/api/drivers`);
  return res.json();
}

export async function submitPermitOrder({ driverIds, states, permitType, effectiveDate }) {
  if (USE_MOCK) {
    const jobId = `JOB-${Math.floor(Math.random() * 9000) + 1000}`;
    const queued = driverIds.length * states.length;
    return mock({ jobId, queued, message: "Permits queued. Automation will stop before payment." }, 800);
  }
  const res = await fetch(`${API_BASE}/api/permits/order`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ driverIds, states, permitType, effectiveDate }),
  });
  return res.json();
}

export async function fetchPermitHistory() {
  if (USE_MOCK) return mock([...MOCK_HISTORY], 400);
  const res = await fetch(`${API_BASE}/api/permits/history`);
  return res.json();
}

export async function fetchBlanketPermits() {
  if (USE_MOCK) return mock([...MOCK_BLANKETS], 300);
  const res = await fetch(`${API_BASE}/api/permits/blankets`);
  return res.json();
}
