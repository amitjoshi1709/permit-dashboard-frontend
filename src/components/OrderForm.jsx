import { useState, useEffect, useRef, useCallback } from "react";
import { STATES, PERMIT_TYPES, fetchDrivers, submitPermitOrder, fetchJobStatus, signalCaptchaSolved } from "../api";
import JobTracker from "./JobTracker";
import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { STATES, PERMIT_TYPES, fetchDrivers, submitPermitOrder, fetchJobStatus, fetchFormFields } from "../api";
import LogConsole from "./LogConsole";
import DynamicFields from "./DynamicFields";

function ts() {
  const d = new Date();
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
}

export default function OrderForm({ onToast }) {
  // ── Form fields (one permit at a time) ──
  const [selectedState, setSelectedState] = useState("");
  const [permitType, setPermitType] = useState("");
  const [effectiveDate, setEffectiveDate] = useState(() => new Date().toISOString().split("T")[0]);
  const [selectedDrivers, setSelectedDrivers] = useState([]);

  // Dynamic form fields (driven by backend schema)
  const [formFields, setFormFields] = useState([]);
  const [extraValues, setExtraValues] = useState({});

  // ── Queue ──
  const [queue, setQueue] = useState([]);
  // Snapshot of the most recently submitted batch — lets you re-queue the same
  // set of permits with one click if a run fails (no need to re-enter data).
  const [lastBatch, setLastBatch] = useState([]);

  // ── Drivers ──
  const [drivers, setDrivers] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  // ── Job processing ──
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

  // Permit types available for the currently selected state.
  // FL-only types (`fl_*`) are hidden unless Florida is selected.
  const availablePermitTypes = useMemo(() => {
    const isFL = selectedState === "FL";
    return PERMIT_TYPES.filter((pt) => !pt.value.startsWith("fl_") || isFL);
  }, [selectedState]);

  // Reset stale permit type selection when state changes
  useEffect(() => {
    if (permitType && !availablePermitTypes.find((pt) => pt.value === permitType)) {
      setPermitType("");
    }
  }, [availablePermitTypes, permitType]);

  // Flatbed requires a reminder that travel begin date must be 2 work days out
  const isFlatbed = permitType === "fl_blanket_flatbed";

  // Fetch dynamic form fields when state or permit type changes
  useEffect(() => {
    if (selectedState && permitType) {
      fetchFormFields([selectedState], permitType)
        .then((fields) => {
          setFormFields(fields);
          setExtraValues({});
        })
        .catch(() => setFormFields([]));
    } else {
      setFormFields([]);
      setExtraValues({});
    }
  }, [selectedState, permitType]);

  function handleExtraFieldChange(key, value) {
    setExtraValues((prev) => ({ ...prev, [key]: value }));
  }

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

  // ── Add to queue ──
  function addToQueue() {
    if (!selectedState || !permitType || selectedDrivers.length === 0) return;

    const stateObj = STATES.find((s) => s.code === selectedState);
    const typeObj = PERMIT_TYPES.find((t) => t.value === permitType);

    const entry = {
      id: Date.now(),
      state: selectedState,
      stateLabel: stateObj?.label || selectedState,
      permitType,
      permitTypeLabel: typeObj?.label || permitType,
      effectiveDate,
      driverIds: [...selectedDrivers],
      driverNames: selectedDrivers.map((id) => {
        const d = drivers.find((dr) => dr.id === id);
        return d ? d.name : `#${id}`;
      }),
      extraFields: Object.keys(extraValues).length > 0 ? { ...extraValues } : null,
    };

    setQueue((prev) => [...prev, entry]);

    // Reset form for next entry (keep date)
    setSelectedState("");
    setPermitType("");
    setSelectedDrivers([]);
    setFormFields([]);
    setExtraValues({});
    setSearch("");
  }

  function removeFromQueue(id) {
    setQueue((prev) => prev.filter((q) => q.id !== id));
  }

  // Clone an existing queue entry (same state, type, date, drivers, extraFields)
  // so you can re-queue the same config without re-typing dimensions/axles/etc.
  function duplicateQueueEntry(id) {
    setQueue((prev) => {
      const src = prev.find((q) => q.id === id);
      if (!src) return prev;
      const clone = {
        ...src,
        id: Date.now() + Math.floor(Math.random() * 1000),
        driverIds: [...src.driverIds],
        driverNames: [...src.driverNames],
        extraFields: src.extraFields ? { ...src.extraFields } : null,
      };
      return [...prev, clone];
    });
  }

  // ── Submit entire queue ──
  const addLog = useCallback((text, status) => {
    setLogMessages((prev) => [...prev, { timestamp: ts(), text, status }]);
  }, []);

  function startPolling(jobId) {
    // Don't double-poll the same job
    if (pollingRef.current.has(jobId)) return;
    setProcessing(true);

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
    pollingRef.current.set(jobId, intervalId);
  }

  // Re-queue the most recently submitted batch (useful when a run fails and
  // you want to retry the exact same set without re-entering data).
  function requeueLastBatch() {
    if (lastBatch.length === 0) return;
    const stamp = Date.now();
    const clones = lastBatch.map((e, i) => ({
      ...e,
      id: stamp + i,
      driverIds: [...e.driverIds],
      driverNames: [...e.driverNames],
      extraFields: e.extraFields ? { ...e.extraFields } : null,
    }));
    setQueue((prev) => [...prev, ...clones]);
  }

  async function handleSubmitQueue() {
    if (queue.length === 0) return;
    setSubmitting(true);
    // Snapshot for re-queue — deep-copy so later mutations can't affect it.
    setLastBatch(queue.map((e) => ({
      ...e,
      driverIds: [...e.driverIds],
      driverNames: [...e.driverNames],
      extraFields: e.extraFields ? { ...e.extraFields } : null,
    })));

    // Group queue entries into a single API call
    // Each queue entry becomes its own batch of (driverIds x [state])
    // We submit them sequentially so each gets its own jobId
    for (const entry of queue) {
      const totalPermits = entry.driverIds.length * (entry.permitType === "trip_fuel" ? 2 : 1);
      addLog(`Submitting ${entry.driverIds.length} driver(s) · ${entry.stateLabel} · ${entry.permitTypeLabel} · ${totalPermits} permit(s)...`, "info");

      try {
        const orderPayload = {
          driverIds: entry.driverIds,
          states: [entry.state],
          permitType: entry.permitType,
          effectiveDate: entry.effectiveDate,
        };
        if (entry.extraFields) {
          orderPayload.extraFields = entry.extraFields;
        }

        const result = await submitPermitOrder(orderPayload);
        addLog(`${result.jobId} queued — processing ${totalPermits} permit(s)...`, "info");
        startPolling(result.jobId);
      } catch {
        addLog(`Error submitting ${entry.stateLabel} · ${entry.permitTypeLabel}`, "error");
      }
    }

    setQueue([]);
    setSubmitting(false);
  }

  const busy = submitting || processing;
  const canAddToQueue = !!selectedState && !!permitType && selectedDrivers.length > 0 && !busy;

  // Count total permits across queue
  const queuePermitCount = queue.reduce((sum, e) => sum + e.driverIds.length * (e.permitType === "trip_fuel" ? 2 : 1), 0);

  return (
    <div className="bg-navy-2 border border-subtle rounded-[14px]">
      <div className="px-[18px] py-3.5 border-b border-subtle flex items-center gap-2.5">
        <div className="text-[13.5px] font-semibold">New Permit Request</div>
        {processing && (
          <span className="text-[11px] text-[#FFD166] bg-permit-orange/15 rounded-md px-2 py-0.5 animate-pulse">
            Processing...
          </span>
        )}
        {queue.length > 0 && !processing && (
          <span className="text-[11px] text-accent-2 bg-accent/10 rounded-md px-2 py-0.5">
            {queue.length} in queue
          </span>
        )}
      </div>

      <div className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Left column — form */}
          <div className="space-y-5">
            {/* State selector — single dropdown */}
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                State
              </label>
              <select
                value={selectedState}
                onChange={(e) => setSelectedState(e.target.value)}
                disabled={busy}
              >
                <option value="">-- Select state --</option>
                {STATES.map((st) => (
                  <option key={st.code} value={st.code}>{st.code} — {st.label}</option>
                ))}
              </select>
            </div>

            {/* Permit Type */}
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                Permit Type
              </label>
              <select
                value={permitType}
                onChange={(e) => setPermitType(e.target.value)}
                disabled={busy}
              >
                <option value="">-- Select permit type --</option>
                {availablePermitTypes.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                Effective Date
              </label>
              <input
                type="date"
                value={effectiveDate}
                onChange={(e) => setEffectiveDate(e.target.value)}
                disabled={busy}
              />
              {isFlatbed && (
                <div className="text-[11px] mt-1.5 px-2.5 py-1.5 rounded-md bg-permit-orange/10 border border-permit-orange/25 text-[#FFD166]">
                  {"\u26a0"} Reminder: travel begin date must be <strong>2 WORK DAYS LATER</strong> than submission.
                </div>
              )}
            </div>

            {/* Dynamic extra fields — driven by backend schema */}
            {formFields.length > 0 && (
              <DynamicFields
                fields={formFields}
                values={extraValues}
                onChange={handleExtraFieldChange}
                disabled={busy}
              />
            )}

            {/* Driver search */}
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                Driver(s)
              </label>

              {selectedDrivers.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {selectedDrivers.map((id) => {
                    const d = drivers.find((dr) => dr.id === id);
                    if (!d) return null;
                    return (
                      <span key={id} className="inline-flex items-center gap-1 bg-accent/15 border border-accent/30 text-accent-2 text-[11px] font-medium px-2 py-1 rounded-md">
                        {d.name}
                        <button
                          onClick={() => removeDriver(id)}
                          disabled={busy}
                          className="hover:text-white transition-colors cursor-pointer leading-none bg-transparent border-none text-accent-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          x
                        </button>
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

            {/* Add to Queue button */}
            <button
              disabled={!canAddToQueue}
              onClick={addToQueue}
              className={`w-full py-2.5 rounded-lg text-[13px] font-medium transition-all font-sans border ${
                canAddToQueue
                  ? "bg-accent/10 border-accent/40 text-accent-2 hover:bg-accent/20 cursor-pointer"
                  : "bg-navy-3 border-subtle text-txt-3 cursor-not-allowed"
              }`}
            >
              + Add to Queue
            </button>

            {/* Payment boundary notice */}
            <div className="rounded-lg px-3.5 py-2.5 text-[12.5px] leading-relaxed bg-permit-orange/10 border border-permit-orange/25 text-[#FFD166] flex items-start gap-2">
              <span className="text-sm flex-shrink-0 mt-px">{"\u26a0"}</span>
              <span>Automation stops before payment. You will complete checkout manually.</span>
            </div>
          </div>

          {/* Right column — queue + submit + log */}
          <div className="space-y-5">
            {/* Queue list */}
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                Permit Queue {queue.length > 0 && `(${queue.length})`}
              </label>

              {queue.length === 0 ? (
                <div className="rounded-lg border border-dashed border-subtle px-4 py-8 text-center">
                  <div className="text-txt-3 text-[12px]">No permits queued yet.</div>
                  <div className="text-txt-3 text-[11px] mt-1 opacity-60">Fill out the form and click "Add to Queue"</div>
                </div>
              ) : (
                <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1">
                  {queue.map((entry) => (
                    <div
                      key={entry.id}
                      className="flex items-start gap-2.5 px-3 py-2.5 rounded-lg bg-navy-3 border border-subtle group"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-[11px] font-bold text-accent-2">{entry.state}</span>
                          <span className="text-[11px] text-txt-2 font-medium">{entry.permitTypeLabel}</span>
                          <span className="text-[10px] text-txt-3">{entry.effectiveDate}</span>
                        </div>
                        <div className="text-[11px] text-txt-3 truncate">
                          {entry.driverNames.join(", ")}
                        </div>
                        {entry.extraFields && (
                          <div className="text-[10px] text-txt-3 opacity-60 mt-0.5">
                            + extra fields attached
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => duplicateQueueEntry(entry.id)}
                          disabled={busy}
                          title="Duplicate this entry"
                          className="text-txt-3 hover:text-accent-2 text-[11px] bg-transparent border-none cursor-pointer disabled:cursor-not-allowed"
                        >
                          ⧉
                        </button>
                        <button
                          onClick={() => removeFromQueue(entry.id)}
                          disabled={busy}
                          title="Remove from queue"
                          className="text-txt-3 hover:text-red-400 text-sm bg-transparent border-none cursor-pointer disabled:cursor-not-allowed"
                        >
                          x
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Submit Queue */}
            <button
              disabled={queue.length === 0 || busy}
              onClick={handleSubmitQueue}
              className={`w-full py-3 rounded-lg text-sm font-medium transition-all font-sans border-none ${
                queue.length > 0 && !busy
                  ? "bg-accent text-white hover:bg-accent-2 cursor-pointer hover:-translate-y-px"
                  : "bg-navy-3 text-txt-3 cursor-not-allowed"
              }`}
            >
              {submitting
                ? "Submitting..."
                : processing
                ? "Processing — please wait..."
                : queue.length > 0
                ? `Submit ${queue.length} request(s) — ${queuePermitCount} permit(s)`
                : "Queue is empty"}
            </button>

            <div className="text-[11px] text-txt-3 text-center -mt-2">
              Each queued request will be processed as a separate job.
            </div>

            {/* Re-queue last submitted batch */}
            {lastBatch.length > 0 && (
              <button
                onClick={requeueLastBatch}
                disabled={busy}
                title="Re-add the last submitted batch to the queue"
                className={`w-full py-2 rounded-lg text-[12px] font-medium transition-all font-sans border ${
                  busy
                    ? "bg-navy-3 border-subtle text-txt-3 cursor-not-allowed"
                    : "bg-navy-3 border-subtle2 text-txt-2 hover:border-accent/40 hover:text-accent-2 cursor-pointer"
                }`}
              >
                {"\u21bb"} Re-queue last batch ({lastBatch.length})
              </button>
            )}

            {/* Re-queue last submitted batch */}
            {lastBatch.length > 0 && (
              <button
                onClick={requeueLastBatch}
                disabled={busy}
                title="Re-add the last submitted batch to the queue"
                className={`w-full py-2 rounded-lg text-[12px] font-medium transition-all font-sans border ${
                  busy
                    ? "bg-navy-3 border-subtle text-txt-3 cursor-not-allowed"
                    : "bg-navy-3 border-subtle2 text-txt-2 hover:border-accent/40 hover:text-accent-2 cursor-pointer"
                }`}
              >
                {"\u21bb"} Re-queue last batch ({lastBatch.length})
              </button>
            )}

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
