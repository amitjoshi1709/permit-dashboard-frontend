import { useState, useEffect } from "react";
import { fetchPermitHistory } from "../api";
import Badge from "./Badge";

const STATUS_FILTERS = ["all", "Active", "Expired", "Pending"];

// Map backend permit_type strings → human-readable labels
const PERMIT_TYPE_LABELS = {
  trip: "Trip",
  fuel: "Fuel",
  trip_fuel: "Trip & Fuel",
  os_ow: "OS/OW",
  fl_blanket_bulk: "FL Blanket — Bulk",
  fl_blanket_inner_bridge: "FL Blanket — Inner Bridge",
  fl_blanket_flatbed: "FL Blanket — Flatbed",
  al_annual_osow: "AL Annual OS/OW",
  // Portal-specific legacy labels
  ITP: "Trip (ITP)",
  MFTP: "Fuel (MFTP)",
};

function formatPermitType(type) {
  if (!type) return "—";
  if (PERMIT_TYPE_LABELS[type]) return PERMIT_TYPE_LABELS[type];
  // Fallback: snake_case → Title Case
  return type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

export const PENDING_CART_KEY = "permitflow_pending_cart";

export default function HistoryTable({ onNavigate, onToast }) {
  const [history, setHistory] = useState([]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [stateFilter, setStateFilter] = useState("all");
  const [driverSearch, setDriverSearch] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());

  function enterSelectMode() {
    setSelectMode(true);
    setSelectedIds(new Set());
  }

  function exitSelectMode() {
    setSelectMode(false);
    setSelectedIds(new Set());
  }

  function load() {
    setLoading(true);
    fetchPermitHistory()
      .then((data) => setHistory(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  // Build unique filter option lists from the data itself
  const uniqueTypes = Array.from(new Set(history.map((p) => p.type).filter(Boolean)));
  const uniqueStates = Array.from(new Set(history.map((p) => p.state).filter(Boolean))).sort();

  // Top (state, type) combos by frequency — powers the "Common" chips row.
  // Combines the two most-used filters (state + permit type) into a single
  // one-click shortcut so dispatchers don't have to reach for both dropdowns.
  const comboCounts = {};
  for (const p of history) {
    if (!p.state || !p.type) continue;
    const key = `${p.state}|${p.type}`;
    if (!comboCounts[key]) {
      comboCounts[key] = { state: p.state, type: p.type, count: 0 };
    }
    comboCounts[key].count += 1;
  }
  const topCombos = Object.values(comboCounts)
    .sort((a, b) => b.count - a.count)
    .slice(0, 6);

  const isComboActive = (combo) =>
    stateFilter === combo.state && typeFilter === combo.type;

  function applyCombo(combo) {
    if (isComboActive(combo)) {
      // Clicking the active combo clears it
      setStateFilter("all");
      setTypeFilter("all");
    } else {
      setStateFilter(combo.state);
      setTypeFilter(combo.type);
    }
  }

  function clearAllFilters() {
    setStateFilter("all");
    setTypeFilter("all");
    setStatusFilter("all");
    setDriverSearch("");
  }

  function toggleSelect(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAllVisible() {
    const visibleIds = filtered.map((p) => p.id);
    const allSelected = visibleIds.every((id) => selectedIds.has(id));
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allSelected) {
        visibleIds.forEach((id) => next.delete(id));
      } else {
        visibleIds.forEach((id) => next.add(id));
      }
      return next;
    });
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  // Stage the selected permits into localStorage, then bounce the user to the
  // Order view. OrderForm reads + clears this key on mount and seeds its cart.
  function duplicateSelectedToCart() {
    const picks = history.filter((p) => selectedIds.has(p.id));
    if (picks.length === 0) return;
    const payload = picks.map((p) => ({
      driverId: p.driverId ?? null,
      driverName: p.driverName || "",
      tractor: p.tractor || "",
      state: p.state || "",
      type: p.type || "",
      sourceId: p.id,
      // Carry the exact dimensions/axles/etc. from the original submission so the
      // duplicated permit re-runs with identical values (critical for FL blanket/OS-OW).
      extraFields: p.extraFields || null,
    }));
    try {
      localStorage.setItem(PENDING_CART_KEY, JSON.stringify(payload));
    } catch {}
    onToast?.("✓", `${picks.length} permit${picks.length > 1 ? "s" : ""} staged in cart`);
    setSelectMode(false);
    setSelectedIds(new Set());
    onNavigate?.("order");
  }

  const hasActiveFilters =
    stateFilter !== "all" ||
    typeFilter !== "all" ||
    statusFilter !== "all" ||
    driverSearch.trim() !== "";

  // Driver suggestions: rank by how many permits they have in history
  // (most common drivers first). Each driver appears with their tractor.
  const driverCounts = {};
  for (const p of history) {
    const name = p.driverName;
    if (!name) continue;
    const key = `${name}||${p.tractor || ""}`;
    if (!driverCounts[key]) {
      driverCounts[key] = { name, tractor: p.tractor || "", count: 0 };
    }
    driverCounts[key].count += 1;
  }
  const allDrivers = Object.values(driverCounts).sort((a, b) => b.count - a.count);

  const q = driverSearch.trim().toLowerCase();
  const driverSuggestions = q
    ? allDrivers.filter((d) =>
        d.name.toLowerCase().includes(q) || d.tractor.toLowerCase().includes(q)
      )
    : allDrivers;

  let filtered = [...history];
  if (typeFilter !== "all") filtered = filtered.filter((p) => p.type === typeFilter);
  if (statusFilter !== "all") filtered = filtered.filter((p) => p.status === statusFilter);
  if (stateFilter !== "all") filtered = filtered.filter((p) => p.state === stateFilter);
  if (driverSearch.trim()) {
    const q = driverSearch.trim().toLowerCase();
    filtered = filtered.filter((p) => {
      const name = (p.driverName || "").toLowerCase();
      const tractor = (p.tractor || "").toLowerCase();
      return name.includes(q) || tractor.includes(q);
    });
  }

  return (
    <div className="bg-navy-2 border border-subtle rounded-[14px]">
      <div className="px-[18px] py-3.5 border-b border-subtle flex items-center gap-2.5">
        <div className="text-[13.5px] font-semibold">Permit History</div>
        <span className="text-[11px] text-txt-3 bg-navy-3 rounded-[10px] px-2 py-0.5">
          {filtered.length} {filtered.length === 1 ? "permit" : "permits"}
        </span>
        {!selectMode ? (
          <button
            onClick={enterSelectMode}
            className="ml-2 inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium cursor-pointer bg-navy-3 border border-subtle2 text-txt-2 hover:bg-accent/10 hover:border-accent/40 hover:text-accent-2 transition-all font-sans"
          >
            ⧉ Duplicate permits
          </button>
        ) : (
          <button
            onClick={exitSelectMode}
            className="ml-2 inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium cursor-pointer bg-transparent border border-subtle2 text-txt-3 hover:text-txt-1 transition-all font-sans"
          >
            Cancel
          </button>
        )}
        <div className="ml-auto flex gap-2">
          <div className="relative">
            <input
              type="text"
              value={driverSearch}
              onChange={(e) => { setDriverSearch(e.target.value); setShowSuggestions(true); }}
              onFocus={() => setShowSuggestions(true)}
              onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
              placeholder="Search driver or tractor..."
              className="!w-[220px] !py-1.5 !px-2.5 !text-xs"
            />
            {driverSearch && (
              <button
                onClick={() => { setDriverSearch(""); setShowSuggestions(false); }}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 text-txt-3 hover:text-txt-1 bg-transparent border-none cursor-pointer text-sm leading-none"
                title="Clear"
              >
                ×
              </button>
            )}
            {showSuggestions && driverSuggestions.length > 0 && (
              <div className="absolute z-20 left-0 right-0 mt-1 bg-navy-2 border border-subtle2 rounded-lg overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.4)] max-h-64 overflow-y-auto">
                {!driverSearch && (
                  <div className="px-2.5 py-1.5 text-[9px] uppercase tracking-wide text-txt-3 bg-navy-3/40 border-b border-subtle">
                    Most Common
                  </div>
                )}
                {driverSuggestions.slice(0, 15).map((d) => (
                  <button
                    key={`${d.name}-${d.tractor}`}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      setDriverSearch(d.name);
                      setShowSuggestions(false);
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-[12px] hover:bg-navy-3 transition-colors cursor-pointer bg-transparent border-none text-txt-1 font-sans"
                  >
                    <div className="w-5 h-5 rounded-full bg-steel flex items-center justify-center text-[8px] font-semibold text-accent-2 flex-shrink-0">
                      {(d.name || "??").substring(0, 2).toUpperCase()}
                    </div>
                    <span className="flex-1 truncate">{d.name}</span>
                    {d.tractor && (
                      <span className="text-[10px] font-mono text-txt-3 flex-shrink-0">{d.tractor}</span>
                    )}
                    <span className="text-[10px] text-txt-3 bg-navy-3 rounded px-1 ml-1 flex-shrink-0">
                      {d.count}
                    </span>
                  </button>
                ))}
                {driverSuggestions.length > 15 && (
                  <div className="px-2.5 py-1.5 text-[10px] text-txt-3 text-center border-t border-subtle">
                    {driverSuggestions.length - 15} more · keep typing
                  </div>
                )}
              </div>
            )}
          </div>
          <select
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
            className="!w-auto !py-1.5 !px-2.5 !text-xs"
          >
            <option value="all">All States</option>
            {uniqueStates.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="!w-auto !py-1.5 !px-2.5 !text-xs"
          >
            <option value="all">All Types</option>
            {uniqueTypes.map((t) => (
              <option key={t} value={t}>{formatPermitType(t)}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Most-common (state + type) combos — one-click shortcuts */}
      {topCombos.length > 0 && (
        <div className="flex items-center gap-2 px-[18px] py-2.5 border-b border-subtle flex-wrap">
          <span className="text-[9px] uppercase tracking-wide text-txt-3 font-medium mr-1">
            Common
          </span>
          {topCombos.map((combo) => {
            const active = isComboActive(combo);
            return (
              <button
                key={`${combo.state}-${combo.type}`}
                onClick={() => applyCombo(combo)}
                className={`inline-flex items-center gap-1.5 px-2.5 py-[5px] rounded-full text-[11px] cursor-pointer transition-all border font-sans ${
                  active
                    ? "bg-accent/20 border-accent/50 text-accent-2 font-medium"
                    : "bg-navy-3 border-subtle text-txt-2 hover:bg-navy-4 hover:text-txt-1"
                }`}
                title={`${combo.state} · ${formatPermitType(combo.type)} — ${combo.count} permits`}
              >
                <span className="font-bold">{combo.state}</span>
                <span className="opacity-80">{formatPermitType(combo.type)}</span>
                <span className={`text-[9px] rounded px-1 ${active ? "bg-accent/25 text-accent-2" : "bg-navy-4 text-txt-3"}`}>
                  {combo.count}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* Filter pills */}
      <div className="flex items-center gap-2.5 px-[18px] py-3 border-b border-subtle">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setStatusFilter(f)}
            className={`px-3 py-[5px] rounded-md text-xs cursor-pointer transition-all border font-sans ${
              statusFilter === f
                ? "bg-accent/15 border-accent/40 text-accent-2 font-medium"
                : "bg-navy-3 border-subtle text-txt-2 hover:bg-navy-4 hover:text-txt-1"
            }`}
          >
            {f === "all" ? "All" : f}
          </button>
        ))}
        {hasActiveFilters && (
          <button
            onClick={clearAllFilters}
            className="text-[11px] text-txt-3 hover:text-permit-red2 bg-transparent border-none cursor-pointer transition-colors font-sans"
          >
            × Clear filters
          </button>
        )}
        <button
          onClick={load}
          className="ml-auto text-xs text-txt-3 hover:text-accent-2 transition-colors cursor-pointer bg-transparent border-none font-sans"
        >
          ↻ Refresh
        </button>
      </div>

      {/* Selection mode banner — visible whenever the user is picking permits */}
      {selectMode && (
        <div className="flex items-center gap-3 px-[18px] py-2.5 bg-accent/10 border-b border-accent/30">
          <span className="text-[12px] text-accent-2 font-medium">
            {selectedIds.size === 0
              ? "Tap permits below to select them for duplication"
              : `${selectedIds.size} selected`}
          </span>
          {selectedIds.size > 0 && (
            <>
              <button
                onClick={duplicateSelectedToCart}
                className="bg-accent text-white border-none px-3 py-[5px] rounded-md text-[11px] font-medium cursor-pointer hover:bg-accent-2 transition-all font-sans"
              >
                ⧉ Add to Cart & Order
              </button>
              <button
                onClick={clearSelection}
                className="text-[11px] text-txt-3 hover:text-txt-1 bg-transparent border-none cursor-pointer transition-colors font-sans"
              >
                Clear selection
              </button>
            </>
          )}
          <button
            onClick={exitSelectMode}
            className="ml-auto text-[11px] text-txt-3 hover:text-txt-1 bg-transparent border-none cursor-pointer transition-colors font-sans"
          >
            Exit
          </button>
        </div>
      )}

      {loading ? (
        <div className="p-10 text-center text-txt-3 text-[13px]">Loading...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-10 text-txt-3 text-[13px]">
          <div className="text-[32px] mb-2.5">📋</div>
          No permits match this filter.
        </div>
      ) : (
        <table className="w-full border-collapse">
          <thead>
            <tr className="text-[11px] text-txt-3 font-medium uppercase tracking-wide bg-navy-3">
              {selectMode && (
                <th className="py-2.5 px-3 border-b border-subtle w-[36px] text-center">
                  <input
                    type="checkbox"
                    checked={filtered.length > 0 && filtered.every((p) => selectedIds.has(p.id))}
                    onChange={toggleSelectAllVisible}
                    className="!w-auto !m-0 cursor-pointer accent-accent"
                    title="Select all visible"
                  />
                </th>
              )}
              <th className="text-left py-2.5 px-3.5 border-b border-subtle w-[80px]">Permit #</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle">Driver</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle w-[90px]">Tractor</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle w-[60px]">State</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle w-[140px]">Type</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle w-[110px]">Effective</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle w-[110px]">Expires</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle w-[90px]">Status</th>
              <th className="py-2.5 px-3.5 border-b border-subtle w-[70px]"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => {
              const initials = (p.driverName || "??").split(",")[0].substring(0, 2).toUpperCase();
              const checked = selectedIds.has(p.id);
              return (
                <tr
                  key={p.id}
                  onClick={selectMode ? () => toggleSelect(p.id) : undefined}
                  className={`transition-colors ${
                    selectMode
                      ? `cursor-pointer ${checked ? "bg-accent/10" : "hover:bg-navy-3"}`
                      : "hover:bg-navy-3"
                  }`}
                >
                  {selectMode && (
                    <td className="py-2.5 px-3 border-b border-subtle text-center">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleSelect(p.id)}
                        onClick={(e) => e.stopPropagation()}
                        className="!w-auto !m-0 cursor-pointer accent-accent"
                      />
                    </td>
                  )}
                  <td className="py-2.5 px-3.5 border-b border-subtle font-mono text-xs text-txt-3">{p.id}</td>
                  <td className="py-2.5 px-3.5 border-b border-subtle">
                    <div className="flex items-center gap-[7px]">
                      <div className="w-6 h-6 rounded-full bg-steel flex items-center justify-center text-[9px] font-semibold text-accent-2 flex-shrink-0">
                        {initials}
                      </div>
                      <span className="text-[13px]">{p.driverName || "—"}</span>
                    </div>
                  </td>
                  <td className="py-2.5 px-3.5 border-b border-subtle font-mono text-[12px] text-txt-2">
                    {p.tractor || "—"}
                  </td>
                  <td className="py-2.5 px-3.5 border-b border-subtle">
                    <span className="text-[11px] font-bold text-accent px-1.5 py-0.5 bg-accent/10 rounded">
                      {p.state || "—"}
                    </span>
                  </td>
                  <td className="py-2.5 px-3.5 border-b border-subtle text-[12.5px] text-txt-1">
                    {formatPermitType(p.type)}
                  </td>
                  <td className="py-2.5 px-3.5 border-b border-subtle text-[13px] text-txt-2">{p.effDate || "—"}</td>
                  <td className="py-2.5 px-3.5 border-b border-subtle text-[13px] text-txt-2">{p.expDate || "—"}</td>
                  <td className="py-2.5 px-3.5 border-b border-subtle"><Badge type={p.status} /></td>
                  <td className="py-2.5 px-3.5 border-b border-subtle">
                    <button className="bg-navy-3 border border-subtle text-txt-2 rounded-md px-2.5 py-1 text-[11px] cursor-pointer hover:bg-navy-4 hover:text-accent-2 hover:border-accent transition-all inline-flex items-center gap-1 font-sans">
                      ↓ PDF
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
