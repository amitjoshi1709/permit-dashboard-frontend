// const API_BASE = "http://127.0.0.1:8000"; // always the backend url, change here when uploading to production only.

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  "https://permit-dev-alb-221372248.us-east-1.elb.amazonaws.com";

// ── Auth token storage ────────────────────────────────────────────────
const TOKEN_KEY = "permitflow_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function logout() {
  setToken(null);
  window.location.reload();
}

async function authFetch(path, options = {}) {
  const token = getToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    setToken(null);
    window.location.reload();
    throw new Error("Session expired");
  }
  return res;
}

export async function login(username, password) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Login failed");
  }
  const data = await res.json();
  setToken(data.token);
  return data;
}

export async function verifyToken() {
  const token = getToken();
  if (!token) return false;
  try {
    const res = await fetch(`${API_BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return res.ok;
  } catch {
    return false;
  }
}

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
  // Alabama-only — gated to AL in OrderForm
  { value: "al_annual_osow",          label: "AL Annual OS/OW" },
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
  const res = await authFetch(`/api/drivers`);
  return res.json();
}

export async function fetchFormFields(states, permitType) {
  const res = await authFetch(`/api/permits/form-fields?states=${states.join(",")}&permitType=${permitType}`);
  const data = await res.json();
  return data.fields || [];
}

export async function submitPermitOrder({ driverIds, states, permitType, effectiveDate, effectiveTime, extraFields }) {
  const payload = {
    driverIds,
    states,
    permitType,
    effectiveDate,
    effectiveTime: effectiveTime || undefined,
    extraFields: (extraFields && Object.keys(extraFields).length > 0) ? extraFields : undefined,
  };
  const res = await authFetch(`/api/permits/order`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function fetchJobStatus(jobId) {
  const res = await authFetch(`/api/permits/status/${jobId}`);
  return res.json();
}

export async function signalCaptchaSolved(jobId) {
  const res = await authFetch(`/api/orders/${jobId}/captcha-solved`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return res.json();
}

export async function fetchPermitHistory() {
  const res = await authFetch(`/api/permits/history`);
  return res.json();
}

export async function fetchBlanketPermits() {
  const res = await authFetch(`/api/permits/blankets`);
  return res.json();
}

// ── Driver CRUD ───────────────────────────────────────────────────────
export async function createDriver(driver) {
  const res = await authFetch(`/api/drivers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(driver),
  });
  return res.json();
}

export async function updateDriver(id, updates) {
  const res = await authFetch(`/api/drivers/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  return res.json();
}

export async function deleteDriver(id) {
  const res = await authFetch(`/api/drivers/${id}`, { method: "DELETE" });
  return res.json();
}

// ── Mega insurance (shared by all F/LP/T drivers) ─────────────────────
export async function fetchMegaInsurance() {
  const res = await authFetch(`/api/drivers/mega-insurance`);
  return res.json();
}

export async function updateMegaInsurance(insurance) {
  const res = await authFetch(`/api/drivers/mega-insurance`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(insurance),
  });
  return res.json();
}

// ── Payment card (encrypted server-side) ─────────────────────────────
export async function fetchPaymentCard() {
  const res = await authFetch(`/api/settings/payment-card`);
  return res.json();
}

export async function updatePaymentCard(card) {
  const res = await authFetch(`/api/settings/payment-card`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(card),
  });
  return res.json();
}
