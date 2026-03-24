import { useState, useEffect } from "react";
import { STATES, PERMIT_TYPES, fetchDrivers, submitPermitOrder } from "../api";
import LogConsole from "./LogConsole";

function ts() {
  const d = new Date();
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
}

export default function OrderForm({ onToast }) {
  const [selectedStates, setSelectedStates] = useState([]);
  const [selectedDrivers, setSelectedDrivers] = useState([]);
  const [permitType, setPermitType] = useState("");
  const [effectiveDate, setEffectiveDate] = useState(() => new Date().toISOString().split("T")[0]);
  const [drivers, setDrivers] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [logMessages, setLogMessages] = useState([]);

  useEffect(() => {
    fetchDrivers().then((data) => {
      setDrivers(data);
      setLoading(false);
    });
  }, []);

  function toggleState(code) {
    setSelectedStates((prev) =>
      prev.includes(code) ? prev.filter((s) => s !== code) : [...prev, code]
    );
  }

  function addDriver(id) {
    if (!selectedDrivers.includes(id)) {
      setSelectedDrivers((prev) => [...prev, id]);
    }
    setSearch("");
  }

  function removeDriver(id) {
    setSelectedDrivers((prev) => prev.filter((d) => d !== id));
  }

  const searchResults = search.trim()
    ? drivers.filter(
        (d) =>
          !selectedDrivers.includes(d.id) &&
          (d.name.toLowerCase().includes(search.toLowerCase()) ||
            d.tractor.toLowerCase().includes(search.toLowerCase()) ||
            d.id.toLowerCase().includes(search.toLowerCase()))
      )
    : [];

  async function handleSubmit() {
    if (selectedDrivers.length === 0 || selectedStates.length === 0 || !permitType) return;
    setSubmitting(true);

    const stateLabel = selectedStates.join(", ");
    const typeLabel = PERMIT_TYPES.find((t) => t.value === permitType)?.label || permitType;
    setLogMessages((prev) => [
      ...prev,
      { timestamp: ts(), text: `Submitting ${selectedDrivers.length} ${typeLabel} permit(s) for ${stateLabel}...` },
    ]);

    try {
      const result = await submitPermitOrder({
        driverIds: selectedDrivers,
        states: selectedStates,
        permitType,
        effectiveDate,
      });

      setLogMessages((prev) => [
        ...prev,
        { timestamp: ts(), text: `${result.jobId} queued. ${result.queued} permit(s) in queue.` },
        { timestamp: ts(), text: result.message },
      ]);

      onToast?.("✓", `Permit order queued · ${result.jobId}`);
      setSelectedDrivers([]);
      setSelectedStates([]);
      setPermitType("");
      setEffectiveDate(new Date().toISOString().split("T")[0]);
      setSearch("");
    } catch {
      setLogMessages((prev) => [
        ...prev,
        { timestamp: ts(), text: "Error submitting permits. Please try again." },
      ]);
      onToast?.("⚠", "Failed to submit permits");
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = selectedDrivers.length > 0 && selectedStates.length > 0 && !!permitType && !submitting;
  const count = selectedDrivers.length * selectedStates.length;
  const stateLabel = selectedStates.length > 0 ? selectedStates.join(", ") : "...";

  return (
    <div className="bg-navy-2 border border-subtle rounded-[14px]">
      <div className="px-[18px] py-3.5 border-b border-subtle flex items-center gap-2.5">
        <div className="text-[13.5px] font-semibold">New Permit Request</div>
      </div>

      <div className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Left column */}
          <div className="space-y-5">
            {/* Permit Type */}
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                Permit Type
              </label>
              <select
                value={permitType}
                onChange={(e) => setPermitType(e.target.value)}
              >
                <option value="">— Select permit type —</option>
                {PERMIT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>

            {/* Effective Date */}
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                Effective Date
              </label>
              <input
                type="date"
                value={effectiveDate}
                onChange={(e) => setEffectiveDate(e.target.value)}
              />
            </div>

            {/* State selector */}
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                Select State(s)
              </label>
              <div className="grid grid-cols-2 gap-2">
                {STATES.map((st) => (
                  <button
                    key={st.code}
                    onClick={() => toggleState(st.code)}
                    className={`flex items-center gap-2 px-3 py-2.5 rounded-lg text-xs border transition-colors cursor-pointer ${
                      selectedStates.includes(st.code)
                        ? "bg-accent/15 border-accent/40 text-accent-2 font-medium"
                        : "bg-navy-3 border-subtle text-txt-2 hover:border-subtle2 hover:text-txt-1"
                    }`}
                  >
                    <span className={`text-[11px] font-bold w-[22px] text-center ${
                      selectedStates.includes(st.code) ? "text-accent-2" : "text-accent"
                    }`}>
                      {st.code}
                    </span>
                    <span className="flex-1 text-left">{st.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Payment boundary notice */}
            <div className="rounded-lg px-3.5 py-2.5 text-[12.5px] leading-relaxed bg-permit-orange/10 border border-permit-orange/25 text-[#FFD166] flex items-start gap-2">
              <span className="text-sm flex-shrink-0 mt-px">⚠</span>
              <span>Automation stops before payment. You will complete checkout manually.</span>
            </div>
          </div>

          {/* Right column */}
          <div className="space-y-5">
            {/* Driver search */}
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                Search Drivers
              </label>

              {/* Selected driver chips */}
              {selectedDrivers.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {selectedDrivers.map((id) => {
                    const d = drivers.find((dr) => dr.id === id);
                    if (!d) return null;
                    return (
                      <span
                        key={id}
                        className="inline-flex items-center gap-1 bg-accent/15 border border-accent/30 text-accent-2 text-[11px] font-medium px-2 py-1 rounded-md"
                      >
                        {d.name}
                        <button
                          onClick={() => removeDriver(id)}
                          className="hover:text-white transition-colors cursor-pointer leading-none bg-transparent border-none text-accent-2 text-sm"
                        >
                          ×
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
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Type a name, tractor #, or ID..."
                  />

                  {searchResults.length > 0 && (
                    <div className="absolute z-10 left-0 right-0 mt-1 bg-navy-2 border border-subtle2 rounded-lg overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.4)]">
                      {searchResults.map((driver) => (
                        <button
                          key={driver.id}
                          onClick={() => addDriver(driver.id)}
                          className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left text-[13px] hover:bg-navy-3 transition-colors cursor-pointer bg-transparent border-none text-txt-1 font-sans"
                        >
                          <div className="w-6 h-6 rounded-full bg-steel flex items-center justify-center text-[9px] font-semibold text-accent-2 flex-shrink-0">
                            {driver.name.substring(0, 2).toUpperCase()}
                          </div>
                          <span>{driver.name}</span>
                          <span className="ml-auto text-[11px] font-mono text-txt-3">{driver.tractor}</span>
                        </button>
                      ))}
                    </div>
                  )}

                  {search.trim() && searchResults.length === 0 && (
                    <div className="absolute z-10 left-0 right-0 mt-1 bg-navy-2 border border-subtle2 rounded-lg px-3 py-2.5 text-[13px] text-txt-3">
                      No drivers found.
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Submit */}
            <button
              disabled={!canSubmit}
              onClick={handleSubmit}
              className={`w-full py-3 rounded-lg text-sm font-medium transition-all font-sans border-none ${
                canSubmit
                  ? "bg-accent text-white hover:bg-accent-2 cursor-pointer hover:-translate-y-px"
                  : "bg-navy-3 text-txt-3 cursor-not-allowed"
              }`}
            >
              {submitting
                ? "Submitting..."
                : `Queue ${count || "..."} permit(s) → ${stateLabel}`}
            </button>

            <div className="text-[11px] text-txt-3 text-center -mt-2">
              This will queue the permit on the portal. Payment is a separate step.
            </div>

            <LogConsole messages={logMessages} />
          </div>
        </div>
      </div>
    </div>
  );
}
