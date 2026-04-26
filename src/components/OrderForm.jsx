import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { STATES, PERMIT_TYPES, COMPANY_TYPES, fetchDrivers, fetchMegaInsurance, submitPermitOrder, fetchJobStatus, fetchFormFields, signalCaptchaSolved } from "../api";
import FL_PERMIT_DEFAULTS from "../../fl_permit_defaults.json";

const PENDING_CART_KEY = "permitflow_pending_cart";
import LogConsole from "./LogConsole";
import DynamicFields from "./DynamicFields";
import JobTracker from "./JobTracker";

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
  const [effectiveTime, setEffectiveTime] = useState(""); // optional; blank = use portal default
  const [selectedDrivers, setSelectedDrivers] = useState([]);

  // Dynamic form fields (driven by backend schema)
  const [formFields, setFormFields] = useState([]);
  const [extraValues, setExtraValues] = useState({});

  // ── Insurance (GA only) ──
  const BLANK_INSURANCE = {
    insuranceCompany: "",
    insuranceEffective: "",
    insuranceExpiration: "",
    policyNumber: "",
  };
  const [megaInsurance, setMegaInsurance] = useState(BLANK_INSURANCE);
  const [insuranceValues, setInsuranceValues] = useState(BLANK_INSURANCE);
  const [insuranceTouched, setInsuranceTouched] = useState(false);
  // For Mega drivers, the fields are locked behind an "Edit" button so the
  // user can't accidentally overwrite policy data already on file.
  const [insuranceUnlocked, setInsuranceUnlocked] = useState(false);

  // ── Queue ──
  const [queue, setQueue] = useState([]);
  const [editingCartId, setEditingCartId] = useState(null);
  const [editCartFields, setEditCartFields] = useState([]);
  const [editCartValues, setEditCartValues] = useState({});
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

  // --- Job tracking (persisted across reloads) ---
  const JOBS_KEY = "permitflow_jobs";
  const [jobs, setJobs] = useState(() => {
    try {
      const raw = localStorage.getItem(JOBS_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });

  // Persist jobs to localStorage on every change
  useEffect(() => {
    try {
      localStorage.setItem(JOBS_KEY, JSON.stringify(jobs));
    } catch {
      // quota or serialization error — ignore
    }
  }, [jobs]);
  const [logMessages, setLogMessages] = useState([]);
  const pollIntervalsRef = useRef({});
  const activeJobIdRef = useRef(null);

  useEffect(() => {
    fetchDrivers()
      .then((data) => {
        const list = Array.isArray(data) ? data : [];
        setDrivers(list);
        setLoading(false);
        // Once drivers are loaded, pull anything the History tab staged for us.
        hydratePendingCart(list);
      })
      .catch(() => {
        setDrivers([]);
        setLoading(false);
      });

    // Preload Mega insurance so we can default GA fields instantly
    fetchMegaInsurance()
      .then((data) => {
        if (data && typeof data === "object") setMegaInsurance({ ...BLANK_INSURANCE, ...data });
      })
      .catch(() => {});

    // Resume polling for any jobs that were still running when the page was reloaded.
    // We read from localStorage directly (not from state) to avoid a stale closure.
    try {
      const raw = localStorage.getItem(JOBS_KEY);
      const stored = raw ? JSON.parse(raw) : [];
      stored.forEach((j) => {
        if (j.status !== "complete" && j.status !== "failed") {
          startPolling(j.jobId);
        }
      });
    } catch {
      // ignore
    }

    return () => {
      Object.values(pollIntervalsRef.current).forEach(clearInterval);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Permit types available for the currently selected state.
  //   FL: only os_ow + blanket variants. (FL does not order trip/fuel/trip_fuel.
  //       The OS/OW flow uses the same portal path as the old FL trip script —
  //       it still clicks the "Trip" radio at the top of the portal.)
  //   Other states: trip / fuel / trip_fuel / os_ow — blanket variants hidden.
  const availablePermitTypes = useMemo(() => {
    const isFL = selectedState === "FL";
    return PERMIT_TYPES.filter((pt) => {
      if (isFL) {
        return pt.value === "os_ow" || pt.value.startsWith("fl_blanket_");
      }
      return !pt.value.startsWith("fl_");
    });
  }, [selectedState]);

  // Reset stale permit type selection when state changes
  useEffect(() => {
    if (permitType && !availablePermitTypes.find((pt) => pt.value === permitType)) {
      setPermitType("");
    }
  }, [availablePermitTypes, permitType]);

  // Flatbed requires a reminder that travel begin date must be 2 work days out
  const isFlatbed = permitType === "fl_blanket_flatbed";

  // Georgia has a 45-minute cooldown between permit purchases
  const isGA = selectedState === "GA";
  const cartHasGA = queue.some((e) => e.state === "GA");

  // Insurance is only required by Georgia right now.
  const insuranceRequired = selectedState === "GA";

  // If every selected driver is a Mega company driver (F/LP/T), we can default
  // the insurance fields to the shared Mega policy. If ANY selected driver is
  // an owner-operator we clear the defaults and force the user to enter fresh
  // info (their own carrier, policy number, etc).
  const allSelectedAreMega = useMemo(() => {
    if (selectedDrivers.length === 0) return false;
    return selectedDrivers.every((id) => {
      const d = drivers.find((dr) => dr.id === id);
      return d && COMPANY_TYPES.includes(d.driverType);
    });
  }, [selectedDrivers, drivers]);

  // Whenever the driver mix changes (and the user hasn't manually edited the
  // fields), refresh the defaults: Mega policy for company drivers, blank for
  // mixed/non-Mega sets. Mega fields are auto-locked; non-Mega are editable.
  useEffect(() => {
    if (!insuranceRequired) return;
    if (insuranceTouched) return;
    if (allSelectedAreMega) {
      setInsuranceValues({ ...megaInsurance });
      setInsuranceUnlocked(false);
    } else {
      setInsuranceValues({ ...BLANK_INSURANCE });
      setInsuranceUnlocked(true);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [insuranceRequired, allSelectedAreMega, megaInsurance, insuranceTouched]);

  // Fields are locked whenever Mega drivers are selected and the user hasn't
  // explicitly chosen to override. Non-Mega sets are always unlocked.
  const insuranceLocked = insuranceRequired && allSelectedAreMega && !insuranceUnlocked;

  function handleInsuranceChange(key, value) {
    if (insuranceLocked) return;
    setInsuranceTouched(true);
    setInsuranceValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleUnlockInsurance() {
    const ok = confirm(
      "This insurance info is already on file for Mega drivers. " +
      "Editing it here only affects this order — it will NOT update the saved Mega policy. " +
      "Continue?"
    );
    if (!ok) return;
    setInsuranceUnlocked(true);
  }

  function resetInsuranceToDefault() {
    setInsuranceTouched(false);
    setInsuranceValues(allSelectedAreMega ? { ...megaInsurance } : { ...BLANK_INSURANCE });
    if (allSelectedAreMega) setInsuranceUnlocked(false);
  }

  const insuranceComplete = !insuranceRequired || (
    insuranceValues.insuranceCompany?.trim() &&
    insuranceValues.insuranceEffective?.trim() &&
    insuranceValues.insuranceExpiration?.trim() &&
    insuranceValues.policyNumber?.trim()
  );

  // Fetch dynamic form fields when state or permit type changes. For Florida
  // permits we seed the form with typical defaults from fl_permit_defaults.json
  // so the dispatcher only has to tweak anything that differs from the norm.
  useEffect(() => {
    if (selectedState && permitType) {
      fetchFormFields([selectedState], permitType)
        .then((fields) => {
          setFormFields(fields);
          if (selectedState === "FL" && FL_PERMIT_DEFAULTS[permitType]) {
            // Deep-copy so edits don't mutate the shared defaults object.
            setExtraValues(JSON.parse(JSON.stringify(FL_PERMIT_DEFAULTS[permitType])));
          } else {
            setExtraValues({});
          }
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
      effectiveTime: effectiveTime || null,
      driverIds: [...selectedDrivers],
      driverNames: selectedDrivers.map((id) => {
        const d = drivers.find((dr) => dr.id === id);
        return d ? d.name : `#${id}`;
      }),
      extraFields: Object.keys(extraValues).length > 0 ? { ...extraValues } : null,
      insurance: insuranceRequired ? { ...insuranceValues } : null,
    };

    setQueue((prev) => [...prev, entry]);

    // Reset form for next entry (keep date)
    setSelectedState("");
    setPermitType("");
    setSelectedDrivers([]);
    setFormFields([]);
    setExtraValues({});
    setInsuranceValues({ ...BLANK_INSURANCE });
    setInsuranceTouched(false);
    setInsuranceUnlocked(false);
    setSearch("");
  }

  function removeFromQueue(id) {
    setQueue((prev) => prev.filter((q) => q.id !== id));
  }

  // Read staged duplicates from History → seed the cart with one entry per
  // unique (state, type) combo, bundling all drivers that shared that combo.
  // We resolve driver IDs by matching driverId first, then by name+tractor.
  function hydratePendingCart(driverList) {
    let pending;
    try {
      const raw = localStorage.getItem(PENDING_CART_KEY);
      if (!raw) return;
      pending = JSON.parse(raw);
      localStorage.removeItem(PENDING_CART_KEY);
    } catch {
      return;
    }
    if (!Array.isArray(pending) || pending.length === 0) return;

    // Group pending picks by (state, type, serialized extraFields).
    // Including extraFields in the key keeps permits with different dimensions/axles
    // in separate queue entries so each row re-submits its exact original values.
    // FL blanket/OS-OW permits have extraFields stored; simple trip/fuel permits
    // have null, so they group together as before.
    const groups = {};
    for (const pick of pending) {
      const extraKey = pick.extraFields ? JSON.stringify(pick.extraFields) : "";
      const key = `${pick.state}|${pick.type}|${extraKey}`;
      if (!groups[key]) {
        groups[key] = {
          state: pick.state,
          type: pick.type,
          extraFields: pick.extraFields || null,
          picks: [],
        };
      }
      groups[key].picks.push(pick);
    }

    const today = new Date().toISOString().split("T")[0];
    const newEntries = [];
    const missing = [];

    Object.values(groups).forEach((group, i) => {
      const stateObj = STATES.find((s) => s.code === group.state);
      const typeObj = PERMIT_TYPES.find((t) => t.value === group.type);
      if (!stateObj || !typeObj) {
        missing.push(`${group.state} ${group.type}`);
        return;
      }

      const driverIds = [];
      const driverNames = [];
      for (const pick of group.picks) {
        let d = null;
        if (pick.driverId != null) {
          d = driverList.find((dr) => dr.id === pick.driverId);
        }
        if (!d && pick.driverName) {
          d = driverList.find(
            (dr) => dr.name === pick.driverName && (dr.tractor || "") === (pick.tractor || "")
          );
        }
        if (!d && pick.driverName) {
          d = driverList.find((dr) => dr.name === pick.driverName);
        }
        if (d) {
          // Intentionally allow duplicates: if the user picked the same
          // driver twice in History, they want two permits ordered.
          driverIds.push(d.id);
          driverNames.push(d.name);
        } else {
          missing.push(pick.driverName || `#${pick.driverId}`);
        }
      }

      if (driverIds.length === 0) return;

      newEntries.push({
        id: Date.now() + i,
        state: group.state,
        stateLabel: stateObj.label,
        permitType: group.type,
        permitTypeLabel: typeObj.label,
        effectiveDate: today,
        effectiveTime: null,
        driverIds,
        driverNames,
        // Carry the originally-submitted dimensions/axles through so submit sends
        // the exact same values the portal received the first time. Deep-clone so
        // edits in one queue row don't mutate another.
        extraFields: group.extraFields ? JSON.parse(JSON.stringify(group.extraFields)) : null,
        insurance: null,
      });
    });

    if (newEntries.length > 0) {
      setQueue((prev) => [...prev, ...newEntries]);
      onToast?.(
        "✓",
        `${newEntries.length} cart item${newEntries.length > 1 ? "s" : ""} ready — set date & review`
      );
    }
    if (missing.length > 0) {
      onToast?.("⚠", `Couldn't resolve ${missing.length} permit(s)`);
    }
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

  // ── Edit cart entry extraFields ──
  async function startEditCartEntry(entry) {
    if (editingCartId === entry.id) {
      setEditingCartId(null);
      return;
    }
    // Fetch the form field schema for this entry's state + permit type
    try {
      const fields = await fetchFormFields([entry.state], entry.permitType);
      setEditCartFields(fields);
      setEditCartValues(entry.extraFields ? { ...entry.extraFields } : {});
      setEditingCartId(entry.id);
    } catch {
      onToast?.("⚠", "Could not load form fields");
    }
  }

  function handleEditCartFieldChange(key, value) {
    setEditCartValues((prev) => ({ ...prev, [key]: value }));
  }

  function saveCartEdit(entryId) {
    setQueue((prev) =>
      prev.map((e) =>
        e.id === entryId
          ? { ...e, extraFields: { ...editCartValues } }
          : e
      )
    );
    setEditingCartId(null);
    onToast?.("✓", "Cart entry updated");
  }

  // ── Submit entire queue ──
  const addLog = useCallback((text, status) => {
    setLogMessages((prev) => [...prev, { timestamp: ts(), text, status }]);
  }, []);

  function startPolling(jobId) {
    // Don't double-poll the same job
    if (pollIntervalsRef.current[jobId]) return;
    setProcessing(true);

    let failCount = 0;
    const MAX_FAILS = 10; // 10 consecutive failures × 3s = 30s before giving up

    const interval = setInterval(async () => {
      try {
        const data = await fetchJobStatus(jobId);
        if (!data || !data.status) {
          // Job expired from Redis — treat as lost
          failCount++;
          if (failCount >= MAX_FAILS) throw new Error("Job expired");
          return;
        }
        failCount = 0; // reset on success

        // Merge backend results into placeholders without duplicating rows.
        // Each backend result is "claimed" exactly once: first by permitId, then
        // by (driverName + permitType) against an unclaimed placeholder.
        setJobs((prev) =>
          prev.map((j) => {
            if (j.jobId !== jobId) return j;
            const results = [...(data.results || [])];
            const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

            // Normalize permit type for matching (handle trip_fuel split etc.)
            const normType = (t) => (t || "").toString().toLowerCase().trim();

            // Track which result indices have been consumed
            const claimed = new Set();

            // Pass 1 — update placeholders by matching criteria
            const merged = j.permits.map((p) => {
              // Already has a permitId → find the exact result
              if (p.permitId) {
                const idx = results.findIndex((r, i) => !claimed.has(i) && r.permitId === p.permitId);
                if (idx !== -1) {
                  claimed.add(idx);
                  const r = results[idx];
                  const isDone = r.status === "success" || r.status === "error";
                  return { ...p, ...r, finishedAt: isDone && !p.finishedAt ? now : p.finishedAt };
                }
                return p;
              }

              // No permitId yet → match by driver + permit type, consuming once
              const idx = results.findIndex(
                (r, i) =>
                  !claimed.has(i) &&
                  r.driverName === p.driverName &&
                  normType(r.permitType) === normType(p.permitType)
              );
              if (idx !== -1) {
                claimed.add(idx);
                const r = results[idx];
                const isDone = r.status === "success" || r.status === "error";
                return { ...p, ...r, finishedAt: isDone && !p.finishedAt ? now : p.finishedAt };
              }

              // Last resort — match by driver only (e.g. wildcard permit type)
              const idx2 = results.findIndex(
                (r, i) => !claimed.has(i) && r.driverName === p.driverName
              );
              if (idx2 !== -1) {
                claimed.add(idx2);
                const r = results[idx2];
                const isDone = r.status === "success" || r.status === "error";
                return { ...p, ...r, finishedAt: isDone && !p.finishedAt ? now : p.finishedAt };
              }

              return p;
            });

            // Pass 2 — any unclaimed results are genuine extras (shouldn't happen
            // with correct placeholders, but don't lose them if it does)
            results.forEach((r, i) => {
              if (claimed.has(i)) return;
              const isDone = r.status === "success" || r.status === "error";
              merged.push({ ...r, state: j.state, finishedAt: isDone ? now : undefined });
            });

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
        failCount++;
        if (failCount >= MAX_FAILS) {
          // Job likely lost (Celery killed, Redis expired, etc.) — stop polling
          clearInterval(interval);
          delete pollIntervalsRef.current[jobId];
          setJobs((prev) =>
            prev.map((j) =>
              j.jobId === jobId ? { ...j, status: "failed" } : j
            )
          );
          const stillRunning = Object.keys(pollIntervalsRef.current).length > 0;
          if (!stillRunning) {
            setProcessing(false);
            setWaitingCaptcha(false);
            activeJobIdRef.current = null;
          }
          onToast?.("⚠", "Job lost — task was cancelled or timed out");
        }
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

    if (cartHasGA) {
      const ok = confirm(
        "Your cart includes Georgia permits. After ordering, the GA portal will lock you out for 45 minutes.\n\n" +
        "Are you sure you've added ALL Georgia permits you need?"
      );
      if (!ok) return;
    }

    setSubmitting(true);
    // Snapshot for re-queue — deep-copy so later mutations can't affect it.
    setLastBatch(queue.map((e) => ({
      ...e,
      driverIds: [...e.driverIds],
      driverNames: [...e.driverNames],
      extraFields: e.extraFields ? { ...e.extraFields } : null,
    })));

    // Merge all GA trip/fuel entries into one API call per permitType so the
    // backend processes them in a single browser session (avoids 45-min cooldown).
    // Group by permitType since the backend needs a single type per job.
    const gaEntries = queue.filter(
      (e) => e.state === "GA" && ["trip", "fuel", "trip_fuel"].includes(e.permitType)
    );
    const otherEntries = queue.filter((e) => !gaEntries.includes(e));

    const submissions = [];

    // Group GA entries by permitType, merge driver IDs within each group
    const gaByType = {};
    for (const e of gaEntries) {
      if (!gaByType[e.permitType]) gaByType[e.permitType] = [];
      gaByType[e.permitType].push(e);
    }
    for (const [pType, entries] of Object.entries(gaByType)) {
      const mergedDriverIds = entries.flatMap((e) => e.driverIds);
      const mergedDriverNames = entries.flatMap((e) => e.driverNames);
      const first = entries[0];
      submissions.push({
        merged: true,
        entries,
        driverIds: mergedDriverIds,
        driverNames: mergedDriverNames,
        state: "GA",
        stateLabel: first.stateLabel,
        permitType: pType,
        permitTypeLabel: first.permitTypeLabel,
        effectiveDate: first.effectiveDate,
        effectiveTime: first.effectiveTime,
        extraFields: first.extraFields,
      });
    }

    for (const entry of otherEntries) {
      submissions.push({ merged: false, entries: [entry], ...entry });
    }

    for (const sub of submissions) {
      const entry = sub;
      // Only GA splits trip_fuel into 2 separate permits; other states (AL) handle it as 1.
      const splitFactor = (entry.permitType === "trip_fuel" && entry.state === "GA") ? 2 : 1;
      const totalPermits = entry.driverIds.length * splitFactor;
      const label = sub.merged
        ? `${gaEntries.length} GA cart item(s) · ${entry.driverIds.length} driver(s) · ${totalPermits} permit(s)`
        : `${entry.driverIds.length} driver(s) · ${entry.stateLabel} · ${entry.permitTypeLabel} · ${totalPermits} permit(s)`;
      addLog(`Submitting ${label}...`, "info");

      try {
        const orderPayload = {
          driverIds: entry.driverIds,
          states: [entry.state],
          permitType: entry.permitType,
          effectiveDate: entry.effectiveDate,
          effectiveTime: entry.effectiveTime || undefined,
          extraFields: entry.extraFields || undefined,
        };

        const result = await submitPermitOrder(orderPayload);
        addLog(`${result.jobId} queued — processing ${totalPermits} permit(s)...`, "info");

        // Build one placeholder row per permit that will be ordered (driver × split).
        // These show up immediately as "Queued" in the tracker so the user sees
        // progress as soon as they hit Submit.
        const placeholders = [];
        for (const dId of entry.driverIds) {
          const d = drivers.find((dr) => dr.id === dId);
          const driverName = d ? (d.name || `${d.firstName || ""} ${d.lastName || ""}`.trim()) : `Driver #${dId}`;
          const tractor = d ? (d.tractor || "") : "";
          // GA trip_fuel → one row for trip + one for fuel; otherwise one row for the selected type.
          const types = (entry.permitType === "trip_fuel" && entry.state === "GA")
            ? ["trip", "fuel"]
            : [entry.permitType];
          for (const t of types) {
            placeholders.push({
              driverName,
              tractor,
              state: entry.state,
              permitType: t,
              status: "pending",
            });
          }
        }

        // Push the new job into state so the tracker picks it up and polling can merge updates.
        setJobs((prev) => [
          ...prev,
          {
            jobId: result.jobId,
            state: entry.state,
            stateLabel: entry.stateLabel,
            permitTypeLabel: entry.permitTypeLabel,
            status: "processing",
            permits: placeholders,
            submittedAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          },
        ]);

        startPolling(result.jobId);
      } catch {
        addLog(`Error submitting ${entry.stateLabel} · ${entry.permitTypeLabel}`, "error");
      }
    }

    setQueue([]);
    setSubmitting(false);
  }

  const busy = submitting || processing;
  const canAddToQueue =
    !!selectedState &&
    !!permitType &&
    selectedDrivers.length > 0 &&
    insuranceComplete &&
    !busy;

  // Count total permits across queue
  const queuePermitCount = queue.reduce((sum, e) => {
    const splitFactor = (e.permitType === "trip_fuel" && e.state === "GA") ? 2 : 1;
    return sum + e.driverIds.length * splitFactor;
  }, 0);

  return (
    <div className="bg-white border border-ink/15">
      <div className="px-[18px] py-3.5 border-b border-ink/15 flex items-center gap-2.5">
        <div className="text-[13.5px] font-semibold">New Permit Request</div>
        {processing && (
          <span className="text-[11px] text-amber-600 bg-amber/15 rounded-sm px-2 py-0.5 animate-pulse">
            Processing...
          </span>
        )}
        {queue.length > 0 && !processing && (
          <span className="text-[11px] text-amber-600 bg-amber/10 rounded-sm px-2 py-0.5">
            {queue.length} in cart
          </span>
        )}
      </div>

      <div className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-start">
          {/* Left column — form */}
          <div className="space-y-4">
            {/* State selector — single dropdown */}
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
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
              {isGA && (
                <div className="text-[11px] mt-1.5 px-2.5 py-1.5 rounded-sm bg-amber/10 border border-amber/30 text-amber-600 flex items-start gap-1.5">
                  <span className="flex-shrink-0 mt-px">{"\u26a0"}</span>
                  <span>Georgia enforces a <strong>45-minute cooldown</strong> between permit purchases. Add all GA drivers/permits to the cart before ordering — you won't be able to order more until the cooldown expires.</span>
                </div>
              )}
            </div>

            {/* Permit Type */}
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
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
              <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
                Effective Date & Time
              </label>
              <div className="flex gap-2">
                <input
                  type="date"
                  value={effectiveDate}
                  onChange={(e) => setEffectiveDate(e.target.value)}
                  disabled={busy}
                  className="flex-1"
                />
                <input
                  type="time"
                  value={effectiveTime}
                  onChange={(e) => setEffectiveTime(e.target.value)}
                  disabled={busy}
                  className="!w-[130px]"
                  placeholder="Optional"
                />
              </div>
              {isFlatbed && (
                <div className="text-[11px] mt-1.5 px-2.5 py-1.5 rounded-sm bg-amber/10 border border-amber/30 text-amber-600">
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

            {/* Driver search — moved above insurance so insurance can auto-fill
                from the selected driver type the moment GA is chosen. */}
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
                Driver(s)
              </label>

              {selectedDrivers.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {selectedDrivers.map((id) => {
                    const d = drivers.find((dr) => dr.id === id);
                    if (!d) return null;
                    return (
                      <span key={id} className="inline-flex items-center gap-1 bg-amber/15 border border-amber/30 text-amber-600 text-[11px] font-medium px-2 py-1 rounded-sm">
                        {d.name}
                        <button
                          onClick={() => removeDriver(id)}
                          disabled={busy}
                          className="hover:text-white transition-colors cursor-pointer leading-none bg-transparent border-none text-amber-600 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          x
                        </button>
                      </span>
                    );
                  })}
                </div>
              )}

              {loading ? (
                <p className="text-ink-400 text-[13px]">Loading drivers...</p>
              ) : (
                <div className="relative">
                  <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Type a name, tractor #, or ID..." disabled={busy} />
                  {searchResults.length > 0 && (
                    <div className="absolute z-10 left-0 right-0 mt-1 bg-white border border-ink/20 rounded-sm overflow-hidden shadow-card max-h-60 overflow-y-auto">
                      {searchResults.slice(0, 20).map((driver) => (
                        <button key={driver.id} onClick={() => addDriver(driver.id)} className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left text-[13px] hover:bg-stone-100 transition-colors cursor-pointer bg-transparent border-none text-steel-900 font-sans">
                          <div className="w-6 h-6 rounded-full bg-stone-100 border border-ink/15 flex items-center justify-center text-[9px] font-semibold text-amber-600 flex-shrink-0">
                            {(driver.name || "").substring(0, 2).toUpperCase()}
                          </div>
                          <span>{driver.name}</span>
                          <span className="ml-auto text-[11px] font-mono text-ink-400">{driver.tractor}</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {search.trim() && searchResults.length === 0 && (
                    <div className="absolute z-10 left-0 right-0 mt-1 bg-white border border-ink/20 rounded-sm px-3 py-2.5 text-[13px] text-ink-400">No drivers found.</div>
                  )}
                </div>
              )}
            </div>

            {/* Insurance — only required by Georgia portal right now */}
            {insuranceRequired && (
              <div className="rounded-sm border border-amber/30 bg-amber/5 p-3.5">
                <div className="flex items-center justify-between mb-2.5">
                  <div className="text-[11px] font-medium uppercase tracking-wide text-amber-600">
                    Insurance Info <span className="text-ink-400 normal-case font-normal">— required for Georgia</span>
                  </div>
                  {allSelectedAreMega && !insuranceUnlocked && selectedDrivers.length > 0 && (
                    <button
                      type="button"
                      onClick={handleUnlockInsurance}
                      disabled={busy}
                      className="text-[10px] text-ink-400 hover:text-amber-600 bg-transparent border-none cursor-pointer transition-colors inline-flex items-center gap-1"
                    >
                      ✎ Edit
                    </button>
                  )}
                  {insuranceTouched && insuranceUnlocked && (
                    <button
                      type="button"
                      onClick={resetInsuranceToDefault}
                      disabled={busy}
                      className="text-[10px] text-ink-400 hover:text-amber-600 bg-transparent border-none cursor-pointer transition-colors"
                    >
                      ↺ Reset to default
                    </button>
                  )}
                </div>

                {selectedDrivers.length === 0 ? (
                  <div className="text-[11px] text-ink-400">
                    Select a driver above to auto-fill insurance info.
                  </div>
                ) : allSelectedAreMega && !insuranceUnlocked ? (
                  <div className="text-[11px] text-ink-400 mb-2.5 flex items-center gap-1.5">
                    <span className="text-[10px]">🔒</span>
                    Using shared Mega insurance on file. Click Edit to override for this order.
                  </div>
                ) : allSelectedAreMega && insuranceUnlocked ? (
                  <div className="text-[11px] text-amber-600 mb-2.5">
                    {"\u26a0"} Overriding Mega insurance for this order only. Changes here do NOT update the saved policy.
                  </div>
                ) : (
                  <div className="text-[11px] text-amber-600 mb-2.5">
                    {"\u26a0"} Non-Mega driver selected — enter their own insurance info.
                  </div>
                )}

                <div className="grid grid-cols-1 gap-2.5">
                  <div>
                    <label className="block text-[10px] font-medium uppercase tracking-wide text-ink-400 mb-1">
                      Insurance Company
                    </label>
                    <input
                      type="text"
                      value={insuranceValues.insuranceCompany || ""}
                      onChange={(e) => handleInsuranceChange("insuranceCompany", e.target.value)}
                      disabled={busy || insuranceLocked}
                      readOnly={insuranceLocked}
                      placeholder="e.g. Prime Property and Casualty"
                      className={insuranceLocked ? "!opacity-70 !cursor-not-allowed" : ""}
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2.5">
                    <div>
                      <label className="block text-[10px] font-medium uppercase tracking-wide text-ink-400 mb-1">
                        Effective Date
                      </label>
                      <input
                        type="text"
                        value={insuranceValues.insuranceEffective || ""}
                        onChange={(e) => handleInsuranceChange("insuranceEffective", e.target.value)}
                        disabled={busy || insuranceLocked}
                        readOnly={insuranceLocked}
                        placeholder="MM/DD/YYYY"
                        className={insuranceLocked ? "!opacity-70 !cursor-not-allowed" : ""}
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] font-medium uppercase tracking-wide text-ink-400 mb-1">
                        Expiration Date
                      </label>
                      <input
                        type="text"
                        value={insuranceValues.insuranceExpiration || ""}
                        onChange={(e) => handleInsuranceChange("insuranceExpiration", e.target.value)}
                        disabled={busy || insuranceLocked}
                        readOnly={insuranceLocked}
                        placeholder="MM/DD/YYYY"
                        className={insuranceLocked ? "!opacity-70 !cursor-not-allowed" : ""}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-[10px] font-medium uppercase tracking-wide text-ink-400 mb-1">
                      Policy Number
                    </label>
                    <input
                      type="text"
                      value={insuranceValues.policyNumber || ""}
                      onChange={(e) => handleInsuranceChange("policyNumber", e.target.value)}
                      disabled={busy || insuranceLocked}
                      readOnly={insuranceLocked}
                      placeholder="e.g. PC24040671"
                      className={insuranceLocked ? "!opacity-70 !cursor-not-allowed" : ""}
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Add to Cart button */}
            <button
              disabled={!canAddToQueue}
              onClick={addToQueue}
              className={`w-full py-2.5 rounded-sm text-[13px] font-medium transition-all font-sans border ${
                canAddToQueue
                  ? "bg-amber/10 border-amber/40 text-amber-600 hover:bg-amber/20 cursor-pointer"
                  : "bg-stone-100 border-ink/15 text-ink-400 cursor-not-allowed"
              }`}
            >
              + Add to Cart
            </button>
          </div>

          {/* Right column — cart + order + tracker */}
          <div className="space-y-4">
            {/* Cart list */}
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
                Cart {queue.length > 0 && `(${queue.length})`}
              </label>

              {queue.length === 0 ? (
                <div className="rounded-sm border border-dashed border-ink/15 px-4 py-6 text-center">
                  <div className="text-ink-400 text-[12px]">Your cart is empty.</div>
                  <div className="text-ink-400 text-[11px] mt-1 opacity-60">Fill out the form and click "Add to Cart"</div>
                </div>
              ) : (
                <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1">
                  {queue.map((entry) => (
                    <div
                      key={entry.id}
                      className="px-3 py-2.5 rounded-sm bg-stone-100 border border-ink/15 group"
                    >
                      <div className="flex items-start gap-2.5">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-[11px] font-bold text-amber-600">{entry.state}</span>
                            <span className="text-[11px] text-ink-500 font-medium">{entry.permitTypeLabel}</span>
                            <span className="text-[10px] text-ink-400">
                              {entry.effectiveDate}{entry.effectiveTime ? ` · ${entry.effectiveTime}` : ""}
                            </span>
                          </div>
                          <div className="text-[11px] text-ink-400 truncate">
                            {entry.driverNames.join(", ")}
                          </div>
                          {entry.extraFields && !editingCartId && (
                            <div className="text-[10px] text-ink-400 opacity-60 mt-0.5">
                              + extra fields attached
                            </div>
                          )}
                        </div>
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          {entry.extraFields && (
                            <button
                              onClick={() => startEditCartEntry(entry)}
                              disabled={busy}
                              title="Edit dimensions & fields"
                              className="text-ink-400 hover:text-amber-600 text-[11px] bg-transparent border-none cursor-pointer disabled:cursor-not-allowed"
                            >
                              {editingCartId === entry.id ? "▾" : "✎"}
                            </button>
                          )}
                          <button
                            onClick={() => duplicateQueueEntry(entry.id)}
                            disabled={busy}
                            title="Duplicate this entry"
                            className="text-ink-400 hover:text-amber-600 text-[11px] bg-transparent border-none cursor-pointer disabled:cursor-not-allowed"
                          >
                            ⧉
                          </button>
                          <button
                            onClick={() => removeFromQueue(entry.id)}
                            disabled={busy}
                            title="Remove from queue"
                            className="text-ink-400 hover:text-red-400 text-sm bg-transparent border-none cursor-pointer disabled:cursor-not-allowed"
                          >
                            x
                          </button>
                        </div>
                      </div>
                      {editingCartId === entry.id && editCartFields.length > 0 && (
                        <div className="mt-2.5 pt-2.5 border-t border-ink/10">
                          <DynamicFields
                            fields={editCartFields}
                            values={editCartValues}
                            onChange={handleEditCartFieldChange}
                            disabled={busy}
                          />
                          <div className="flex gap-2 mt-2.5">
                            <button
                              onClick={() => saveCartEdit(entry.id)}
                              disabled={busy}
                              className="bg-amber text-white border-none px-3 py-1.5 rounded-sm text-[11px] font-medium cursor-pointer hover:bg-amber-600 transition-all font-sans"
                            >
                              Save Changes
                            </button>
                            <button
                              onClick={() => setEditingCartId(null)}
                              className="bg-transparent border border-ink/20 text-ink-500 px-3 py-1.5 rounded-sm text-[11px] cursor-pointer hover:bg-bone-3 transition-all font-sans"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Order cart */}
            <button
              disabled={queue.length === 0 || busy}
              onClick={handleSubmitQueue}
              className={`w-full py-3 rounded-sm text-sm font-medium transition-all font-sans border-none ${
                queue.length > 0 && !busy
                  ? "bg-amber text-white hover:bg-amber-600 cursor-pointer hover:-translate-y-px"
                  : "bg-stone-100 text-ink-400 cursor-not-allowed"
              }`}
            >
              {submitting
                ? "Ordering..."
                : processing
                ? "Processing — please wait..."
                : queue.length > 0
                ? `Order ${queue.length} item(s) — ${queuePermitCount} permit(s)`
                : "Cart is empty"}
            </button>

            {cartHasGA && !busy && (
              <div className="text-[11px] px-3 py-2 rounded-sm bg-amber/10 border border-amber/30 text-amber-600 flex items-start gap-1.5">
                <span className="flex-shrink-0 mt-px">{"\u26a0"}</span>
                <span>Your cart includes Georgia permits. Make sure <strong>all GA permits</strong> are in the cart — the portal locks you out for 45 minutes after ordering.</span>
              </div>
            )}

            {lastBatch.length > 0 && (
              <button
                onClick={requeueLastBatch}
                disabled={busy}
                title="Re-add the last order's items to your cart"
                className={`w-full py-2 rounded-sm text-[12px] font-medium transition-all font-sans border ${
                  busy
                    ? "bg-stone-100 border-ink/15 text-ink-400 cursor-not-allowed"
                    : "bg-stone-100 border-ink/20 text-ink-500 hover:border-amber/40 hover:text-amber-600 cursor-pointer"
                }`}
              >
                {"\u21bb"} Re-add last order to cart ({lastBatch.length})
              </button>
            )}

            {waitingCaptcha && (
              <button onClick={handleCaptchaContinue} className="w-full py-3 rounded-sm text-sm font-semibold transition-all font-sans border-none bg-[#e85d04] text-white hover:bg-[#d45303] cursor-pointer animate-pulse">
                CAPTCHA Detected — Solve in Browser, Then Click Here to Continue
              </button>
            )}

            <JobTracker
              jobs={jobs}
              onClear={() => {
                setJobs([]);
                try { localStorage.removeItem(JOBS_KEY); } catch { /* ignore */ }
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
