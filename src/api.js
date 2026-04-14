const API_BASE = "http://127.0.0.1:8000"; // always the backend url, change here when uploading to production only.

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
  { code: "AR", label: "Arkansas" },
];

// ── Permit types ──────────────────────────────────────────────────────
export const PERMIT_TYPES = [
  { value: "trip_fuel", label: "Trip and Fuel" },
  { value: "os_ow", label: "OS/OW" },
  { value: "trip", label: "Trip" },
  { value: "fuel", label: "Fuel" },
  // Florida-only blanket variants — gated to FL in OrderForm
  { value: "fl_blanket_bulk",         label: "FL Blanket Bulk" },
  { value: "fl_blanket_inner_bridge", label: "FL Blanket Inner Bridge" },
  { value: "fl_blanket_flatbed",      label: "FL Blanket Flatbed" },
];

// ── Driver type constants ─────────────────────────────────────────────
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

// ── API functions ─────────────────────────────────────────────────────
export async function fetchDrivers() {
  const res = await fetch(`${API_BASE}/api/drivers`);
  return res.json();
}

export async function fetchFormFields(states, permitType) {
  const res = await fetch(`${API_BASE}/api/permits/form-fields?states=${states.join(",")}&permitType=${permitType}`);
  const data = await res.json();
  return data.fields || [];
}

export async function submitPermitOrder({ driverIds, states, permitType, effectiveDate, extraFields }) {
  const payload = { driverIds, states, permitType, effectiveDate };
  if (extraFields && Object.keys(extraFields).length > 0) payload.extraFields = extraFields;
  const res = await fetch(`${API_BASE}/api/permits/order`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function fetchJobStatus(jobId) {
  const res = await fetch(`${API_BASE}/api/permits/status/${jobId}`);
  return res.json();
}

export async function signalCaptchaSolved(jobId) {
  const res = await fetch(`${API_BASE}/api/orders/${jobId}/captcha-solved`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return res.json();
}

export async function fetchPermitHistory() {
  const res = await fetch(`${API_BASE}/api/permits/history`);
  return res.json();
}

export async function fetchBlanketPermits() {
  const res = await fetch(`${API_BASE}/api/permits/blankets`);
  return res.json();
}

// ── Driver CRUD ───────────────────────────────────────────────────────
export async function createDriver(driver) {
  const res = await fetch(`${API_BASE}/api/drivers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(driver),
  });
  return res.json();
}

export async function updateDriver(id, updates) {
  const res = await fetch(`${API_BASE}/api/drivers/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  return res.json();
}

export async function deleteDriver(id) {
  const res = await fetch(`${API_BASE}/api/drivers/${id}`, { method: "DELETE" });
  return res.json();
}
