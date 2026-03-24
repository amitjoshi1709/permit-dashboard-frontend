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
export const DRIVER_TYPES = [
  { value: "F", label: "F — Fleet" },
  { value: "LP", label: "LP — Lease Purchase" },
  { value: "T", label: "T — Temporary" },
  { value: "OT", label: "OT — Owner/Operator (Truck)" },
  { value: "BC", label: "BC — Business Carrier" },
  { value: "AC", label: "AC — Authority Carrier" },
  { value: "WC", label: "WC — Walk-in Carrier" },
];

export const COMPANY_TYPES = ["F", "LP", "T"];

export const COMPANY_DEFAULTS = {
  usdot: "2582238",
  insuranceCompany: "Prime Property and Casualty",
  insuranceEffective: "04/11/2025",
  insuranceExpiration: "04/11/2026",
  policyNumber: "PC24040671",
};

let MOCK_DRIVERS = [
  { id: "D001", firstName: "Jonattan", lastName: "Vazquez Perez", tractor: "F894", driverType: "F", year: "2016", make: "Freightliner", vin: "3HSDJAPRXGN030818", tagNumber: "FL-1234", tagState: "FL", usdot: "2582238", fein: "", insuranceCompany: "Prime Property and Casualty", insuranceEffective: "04/11/2025", insuranceExpiration: "04/11/2026", policyNumber: "PC24040671" },
  { id: "D002", firstName: "Mario", lastName: "Lopez", tractor: "F712", driverType: "LP", year: "2018", make: "Peterbilt", vin: "1XPBDP9X3HD123456", tagNumber: "FL-5678", tagState: "FL", usdot: "2582238", fein: "", insuranceCompany: "Prime Property and Casualty", insuranceEffective: "04/11/2025", insuranceExpiration: "04/11/2026", policyNumber: "PC24040671" },
  { id: "D003", firstName: "Roberto", lastName: "Campos", tractor: "T211", driverType: "OT", year: "2019", make: "Kenworth", vin: "3AKJHHDR7JSJA4532", tagNumber: "TX-9012", tagState: "TX", usdot: "3847291", fein: "84-7291003", insuranceCompany: "National Indemnity", insuranceEffective: "01/15/2026", insuranceExpiration: "01/15/2027", policyNumber: "NI-2026-4532" },
  { id: "D004", firstName: "Pedro", lastName: "Gomez", tractor: "T305", driverType: "BC", year: "2020", make: "Freightliner", vin: "1FUJHHDR0HLHU8932", tagNumber: "GA-3456", tagState: "GA", usdot: "4112983", fein: "41-1298300", insuranceCompany: "Great West Casualty", insuranceEffective: "06/01/2025", insuranceExpiration: "06/01/2026", policyNumber: "GW-8932-26" },
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
  if (USE_MOCK) {
    return mock(MOCK_DRIVERS.map((d) => ({ ...d, name: `${d.firstName} ${d.lastName}` })), 300);
  }
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

// ── Driver CRUD ───────────────────────────────────────────────────────
export async function createDriver(driver) {
  if (USE_MOCK) {
    const maxId = MOCK_DRIVERS.reduce((max, d) => Math.max(max, parseInt(d.id.slice(1))), 0);
    const newDriver = { ...driver, id: `D${String(maxId + 1).padStart(3, "0")}` };
    MOCK_DRIVERS.push(newDriver);
    return mock({ ...newDriver, name: `${newDriver.firstName} ${newDriver.lastName}` }, 300);
  }
  const res = await fetch(`${API_BASE}/api/drivers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(driver),
  });
  return res.json();
}

export async function updateDriver(id, updates) {
  if (USE_MOCK) {
    const idx = MOCK_DRIVERS.findIndex((d) => d.id === id);
    if (idx === -1) throw new Error("Driver not found");
    MOCK_DRIVERS[idx] = { ...MOCK_DRIVERS[idx], ...updates };
    return mock({ ...MOCK_DRIVERS[idx] }, 300);
  }
  const res = await fetch(`${API_BASE}/api/drivers/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  return res.json();
}

export async function deleteDriver(id) {
  if (USE_MOCK) {
    MOCK_DRIVERS = MOCK_DRIVERS.filter((d) => d.id !== id);
    return mock({ success: true }, 300);
  }
  const res = await fetch(`${API_BASE}/api/drivers/${id}`, { method: "DELETE" });
  return res.json();
}
