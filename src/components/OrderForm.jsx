import { useState, useEffect, useRef, useCallback } from "react";
import { STATES, PERMIT_TYPES, fetchDrivers, submitPermitOrder, fetchJobStatus, signalCaptchaSolved } from "../api";
import JobTracker from "./JobTracker";

export default function OrderForm({ onToast }) {
  // --- Form fields ---
  const [selectedState, setSelectedState] = useState("");
  const [selectedDrivers, setSelectedDrivers] = useState([]);
  const [permitType, setPermitType] = useState("");
  const [effectiveDate, setEffectiveDate] = useState(() => new Date().toISOString().split("T")[0]);
  const [effectiveTime, setEffectiveTime] = useState("12:00");

  // --- Cart ---
  const [cart, setCart] = useState([]);

  // --- Shared state ---
  const [drivers, setDrivers] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [waitingCaptcha, setWaitingCaptcha] = useState(false);

  // --- Job tracking (replaces log messages) ---
  const [jobs, setJobs] = useState([]);
  const pollIntervalsRef = useRef({});
  const activeJobIdRef = useRef(null);

  useEffect(() => {
    fetchDrivers()
      .then((data) => {
        setDrivers(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(() => {
        setDrivers([]);
        setLoading(false);
      });
    return () => {
      Object.values(pollIntervalsRef.current).forEach(clearInterval);
    };
  }, []);

  function addDriver(id) {
    if (!selectedDrivers.includes(id)) setSelectedDrivers((prev) => [...prev, id]);
    setSearch("");
  }

  function removeDriver(id) {
    setSelectedDrivers((prev) => prev.filter((d) => d !== id));
  }

  const searchResults = search.trim()
    ? drivers.filter((d) => {
        if (selectedDrivers.includes(d.id)) return false;
        const q = search.toLowerCase();
        return (d.name || "").toLowerCase().includes(q)
          || (d.tractor || "").toLowerCase().includes(q)
          || String(d.id || "").toLowerCase().includes(q);
      })
    : [];

  // --- Cart logic ---
  const canAddToCart = selectedDrivers.length > 0 && selectedState && permitType;

  function addToCart() {
    if (!canAddToCart) return;
    setCart((prev) => [
      ...prev,
      {
        id: Date.now(),
        driverIds: [...selectedDrivers],
        state: selectedState,
        permitType,
        effectiveDate,
        effectiveTime,
        driverNames: selectedDrivers.map((id) => {
          const d = drivers.find((dr) => dr.id === id);
          return d ? d.name : `#${id}`;
        }),
        stateLabel: STATES.find((s) => s.code === selectedState)?.label || selectedState,
        typeLabel: PERMIT_TYPES.find((t) => t.value === permitType)?.label || permitType,
      },
    ]);
    setSelectedDrivers([]);
    setSelectedState("");
    setPermitType("");
    setSearch("");
  }

  function removeFromCart(cartId) {
    setCart((prev) => prev.filter((item) => item.id !== cartId));
  }

  // --- Job polling (supports multiple concurrent jobs) ---
  function startPolling(jobId) {
    activeJobIdRef.current = jobId;

    const interval = setInterval(async () => {
      try {
        const data = await fetchJobStatus(jobId);

        // Merge backend results into initial placeholders so all permits stay visible.
        // Backend results have permitId; match by driverName+permitType or just append.
        setJobs((prev) =>
          prev.map((j) => {
            if (j.jobId !== jobId) return j;
            const results = data.results || [];
            const resultIds = new Set(results.map((r) => r.permitId));

            const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

            // Update existing placeholders with real results
            const merged = j.permits.map((p) => {
              // Find a matching result by driver name
              const match = results.find(
                (r) => r.driverName === p.driverName && !p.permitId && r.status !== undefined
              );
              if (match) {
                const isDone = match.status === "success" || match.status === "error";
                return { ...p, ...match, finishedAt: isDone && !p.finishedAt ? now : p.finishedAt };
              }
              // If this permit already has a permitId, update from results
              if (p.permitId) {
                const updated = results.find((r) => r.permitId === p.permitId);
                if (updated) {
                  const isDone = updated.status === "success" || updated.status === "error";
                  return { ...p, ...updated, finishedAt: isDone && !p.finishedAt ? now : p.finishedAt };
                }
              }
              return p;
            });

            // Add any results not already in placeholders (e.g., trip_fuel expansion)
            for (const r of results) {
              const alreadyTracked = merged.some(
                (m) => m.permitId === r.permitId || (m.driverName === r.driverName && m.status === r.status && m.permitType === r.permitType)
              );
              if (!alreadyTracked) {
                const isDone = r.status === "success" || r.status === "error";
                merged.push({ ...r, state: j.state, finishedAt: isDone ? now : undefined });
              }
            }

            return { ...j, status: data.status, permits: merged, summary: data.summary };
          })
        );

        // CAPTCHA
        if (data.status === "waiting_captcha") {
          setWaitingCaptcha(true);
          activeJobIdRef.current = jobId;
        } else if (waitingCaptcha && activeJobIdRef.current === jobId) {
          setWaitingCaptcha(false);
        }

        // Done
        if (data.status === "complete" || data.status === "failed") {
          clearInterval(interval);
          delete pollIntervalsRef.current[jobId];

          // Check if ALL jobs are done
          const stillRunning = Object.keys(pollIntervalsRef.current).length > 0;
          if (!stillRunning) {
            setProcessing(false);
            setWaitingCaptcha(false);
            activeJobIdRef.current = null;
          }

          if (data.summary) {
            const { succeeded, failed, total } = data.summary;
            if (failed === 0) {
              onToast?.("✓", `${succeeded} permit${succeeded > 1 ? "s" : ""} completed`);
            } else {
              onToast?.("⚠", `${failed} of ${total} permits failed`);
            }
          }
        }
      } catch {
        // skip this tick
      }
    }, 3000);

    pollIntervalsRef.current[jobId] = interval;
  }

  async function handleCaptchaContinue() {
    const jobId = activeJobIdRef.current;
    if (!jobId) return;
    try {
      await signalCaptchaSolved(jobId);
      setWaitingCaptcha(false);
    } catch {
      // ignore
    }
  }

  async function handleSubmitCart() {
    if (cart.length === 0) return;
    setSubmitting(true);
    setProcessing(true);

    const allItems = [...cart];
    setCart([]);

    for (const item of allItems) {
      try {
        const result = await submitPermitOrder({
          driverIds: item.driverIds,
          states: [item.state],
          permitType: item.permitType,
          effectiveDate: item.effectiveDate,
          effectiveTime: item.effectiveTime,
        });

        // Build initial permit placeholders for the tracker
        const initialPermits = item.driverIds.map((dId) => {
          const d = drivers.find((dr) => dr.id === dId);
          return {
            driverName: d ? d.name : `Driver #${dId}`,
            tractor: d ? d.tractor : "",
            state: item.state,
            permitType: item.typeLabel,
            status: "pending",
          };
        });

        setJobs((prev) => [
          ...prev,
          {
            jobId: result.jobId,
            state: item.state,
            status: "processing",
            permits: initialPermits,
            summary: null,
          },
        ]);

        startPolling(result.jobId);
      } catch {
        onToast?.("⚠", `Failed to submit ${item.stateLabel} · ${item.typeLabel}`);
      }
    }

    setSubmitting(false);
  }

  const busy = submitting || processing;
  const cartPermitCount = cart.reduce((sum, item) => {
    return sum + item.driverIds.length * (item.permitType === "trip_fuel" ? 2 : 1);
  }, 0);

  return (
    <div className="bg-navy-2 border border-subtle rounded-[14px]">
      <div className="px-[18px] py-3.5 border-b border-subtle flex items-center gap-2.5">
        <div className="text-[13.5px] font-semibold">New Permit Request</div>
        {processing && (
          <span className="text-[11px] text-[#FFD166] bg-permit-orange/15 rounded-md px-2 py-0.5 animate-pulse">
            Processing...
          </span>
        )}
        {cart.length > 0 && !processing && (
          <span className="text-[11px] text-accent-2 bg-accent/15 rounded-md px-2 py-0.5">
            {cart.length} item{cart.length > 1 ? "s" : ""} in cart
          </span>
        )}
      </div>

      <div className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Left column */}
          <div className="space-y-5">
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">Permit Type</label>
              <select value={permitType} onChange={(e) => setPermitType(e.target.value)} disabled={busy}>
                <option value="">— Select permit type —</option>
                {PERMIT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">Effective Date & Time</label>
              <div className="flex gap-2">
                <input type="date" value={effectiveDate} onChange={(e) => setEffectiveDate(e.target.value)} disabled={busy} className="flex-1" />
                <input type="time" value={effectiveTime} onChange={(e) => setEffectiveTime(e.target.value)} disabled={busy} className="w-[120px]" />
              </div>
              <div className="text-[10px] text-txt-3 mt-1">Time applies to portals that require it (e.g., Georgia ITP)</div>
            </div>

            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">State</label>
              <select value={selectedState} onChange={(e) => setSelectedState(e.target.value)} disabled={busy}>
                <option value="">— Select state —</option>
                {STATES.map((st) => (
                  <option key={st.code} value={st.code}>{st.code} — {st.label}</option>
                ))}
              </select>
            </div>

            <div className="rounded-lg px-3.5 py-2.5 text-[12.5px] leading-relaxed bg-permit-orange/10 border border-permit-orange/25 text-[#FFD166] flex items-start gap-2">
              <span className="text-sm flex-shrink-0 mt-px">⚠</span>
              <span>Automation stops before payment. You will complete checkout manually.</span>
            </div>
          </div>

          {/* Right column */}
          <div className="space-y-5">
            {/* Driver search */}
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">Search Drivers</label>

              {selectedDrivers.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {selectedDrivers.map((id) => {
                    const d = drivers.find((dr) => dr.id === id);
                    if (!d) return null;
                    return (
                      <span key={id} className="inline-flex items-center gap-1 bg-accent/15 border border-accent/30 text-accent-2 text-[11px] font-medium px-2 py-1 rounded-md">
                        {d.name}
                        <button onClick={() => removeDriver(id)} disabled={busy} className="hover:text-white transition-colors cursor-pointer leading-none bg-transparent border-none text-accent-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed">×</button>
                      </span>
                    );
                  })}
                </div>
              )}

              {loading ? (
                <p className="text-txt-3 text-[13px]">Loading drivers...</p>
              ) : (
                <div className="relative">
                  <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Type a name, tractor #, or ID..." disabled={busy} />
                  {searchResults.length > 0 && (
                    <div className="absolute z-10 left-0 right-0 mt-1 bg-navy-2 border border-subtle2 rounded-lg overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.4)] max-h-60 overflow-y-auto">
                      {searchResults.slice(0, 20).map((driver) => (
                        <button key={driver.id} onClick={() => addDriver(driver.id)} className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left text-[13px] hover:bg-navy-3 transition-colors cursor-pointer bg-transparent border-none text-txt-1 font-sans">
                          <div className="w-6 h-6 rounded-full bg-steel flex items-center justify-center text-[9px] font-semibold text-accent-2 flex-shrink-0">
                            {(driver.name || "").substring(0, 2).toUpperCase()}
                          </div>
                          <span>{driver.name}</span>
                          <span className="ml-auto text-[11px] font-mono text-txt-3">{driver.tractor}</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {search.trim() && searchResults.length === 0 && (
                    <div className="absolute z-10 left-0 right-0 mt-1 bg-navy-2 border border-subtle2 rounded-lg px-3 py-2.5 text-[13px] text-txt-3">No drivers found.</div>
                  )}
                </div>
              )}
            </div>

            {/* Add to Cart */}
            <button
              disabled={!canAddToCart || busy}
              onClick={addToCart}
              className={`w-full py-2.5 rounded-lg text-sm font-medium transition-all font-sans border ${
                canAddToCart && !busy
                  ? "bg-navy-3 border-accent/40 text-accent-2 hover:bg-accent/15 cursor-pointer"
                  : "bg-navy-3 border-subtle text-txt-3 cursor-not-allowed"
              }`}
            >
              + Add to Cart
            </button>

            {/* Cart */}
            {cart.length > 0 && (
              <div className="space-y-2">
                <div className="text-[11px] font-medium uppercase tracking-wide text-txt-3">
                  Cart ({cart.length} item{cart.length > 1 ? "s" : ""} · {cartPermitCount} permit{cartPermitCount > 1 ? "s" : ""})
                </div>
                {cart.map((item) => (
                  <div key={item.id} className="flex items-center gap-2 bg-navy-3 border border-subtle rounded-lg px-3 py-2">
                    <div className="flex-1 min-w-0">
                      <div className="text-[12px] text-txt-1 truncate">
                        <span className="font-semibold text-accent-2">{item.state}</span>
                        {" · "}{item.typeLabel}{" · "}{item.effectiveDate}
                      </div>
                      <div className="text-[11px] text-txt-3 truncate">{item.driverNames.join(", ")}</div>
                    </div>
                    <button onClick={() => removeFromCart(item.id)} disabled={busy} className="text-txt-3 hover:text-red text-sm cursor-pointer bg-transparent border-none disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0">×</button>
                  </div>
                ))}
              </div>
            )}

            {/* Order button */}
            <button
              disabled={cart.length === 0 || busy}
              onClick={handleSubmitCart}
              className={`w-full py-3 rounded-lg text-sm font-medium transition-all font-sans border-none ${
                cart.length > 0 && !busy
                  ? "bg-accent text-white hover:bg-accent-2 cursor-pointer hover:-translate-y-px"
                  : "bg-navy-3 text-txt-3 cursor-not-allowed"
              }`}
            >
              {submitting ? "Submitting..." : processing ? "Processing — please wait..."
                : cart.length > 0 ? `Order ${cartPermitCount} Permit${cartPermitCount > 1 ? "s" : ""}` : "Add items to cart to order"}
            </button>

            <div className="text-[11px] text-txt-3 text-center -mt-2">
              This will queue the permit on the portal. Payment is a separate step.
            </div>

            {waitingCaptcha && (
              <button onClick={handleCaptchaContinue} className="w-full py-3 rounded-lg text-sm font-semibold transition-all font-sans border-none bg-[#e85d04] text-white hover:bg-[#d45303] cursor-pointer animate-pulse">
                CAPTCHA Detected — Solve in Browser, Then Click Here to Continue
              </button>
            )}

            {/* Job tracker replaces the old terminal log */}
            <JobTracker jobs={jobs} onClear={() => setJobs([])} />
          </div>
        </div>
      </div>
    </div>
  );
}
