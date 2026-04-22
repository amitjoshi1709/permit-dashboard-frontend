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
    <div className="bg-white border border-ink/15">
      <div className="px-[18px] py-3.5 border-b border-ink/15 flex items-center gap-2.5">
        <div className="text-[13.5px] font-semibold">Permit History</div>
        <span className="text-[11px] text-ink-400 bg-stone-100 rounded-sm px-2 py-0.5">
          {filtered.length} {filtered.length === 1 ? "permit" : "permits"}
        </span>
        {!selectMode ? (
          <button
            onClick={enterSelectMode}
            className="ml-2 inline-flex items-center gap-1 px-2.5 py-1 rounded-sm text-[11px] font-medium cursor-pointer bg-stone-100 border border-ink/20 text-ink-500 hover:bg-amber/10 hover:border-amber/40 hover:text-amber-600 transition-all font-sans"
          >
            ⧉ Duplicate permits
          </button>
        ) : (
          <button
            onClick={exitSelectMode}
            className="ml-2 inline-flex items-center gap-1 px-2.5 py-1 rounded-sm text-[11px] font-medium cursor-pointer bg-transparent border border-ink/20 text-ink-400 hover:text-steel-900 transition-all font-sans"
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
                className="absolute right-1.5 top-1/2 -translate-y-1/2 text-ink-400 hover:text-steel-900 bg-transparent border-none cursor-pointer text-sm leading-none"
                title="Clear"
              >
                ×
              </button>
            )}
            {showSuggestions && driverSuggestions.length > 0 && (
              <div className="absolute z-20 left-0 right-0 mt-1 bg-white border border-ink/20 rounded-sm overflow-hidden shadow-card max-h-64 overflow-y-auto">
                {!driverSearch && (
                  <div className="px-2.5 py-1.5 text-[9px] uppercase tracking-wide text-ink-400 bg-stone-100/40 border-b border-ink/15">
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
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-[12px] hover:bg-stone-100 transition-colors cursor-pointer bg-transparent border-none text-steel-900 font-sans"
                  >
                    <div className="w-5 h-5 rounded-full bg-stone-100 border border-ink/15 flex items-center justify-center text-[8px] font-semibold text-amber-600 flex-shrink-0">
                      {(d.name || "??").substring(0, 2).toUpperCase()}
                    </div>
                    <span className="flex-1 truncate">{d.name}</span>
                    {d.tractor && (
                      <span className="text-[10px] font-mono text-ink-400 flex-shrink-0">{d.tractor}</span>
                    )}
                    <span className="text-[10px] text-ink-400 bg-stone-100 rounded px-1 ml-1 flex-shrink-0">
                      {d.count}
                    </span>
                  </button>
                ))}
                {driverSuggestions.length > 15 && (
                  <div className="px-2.5 py-1.5 text-[10px] text-ink-400 text-center border-t border-ink/15">
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
        <div className="flex items-center gap-2 px-[18px] py-2.5 border-b border-ink/15 flex-wrap">
          <span className="text-[9px] uppercase tracking-wide text-ink-400 font-medium mr-1">
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
                    ? "bg-amber/20 border-amber/50 text-amber-600 font-medium"
                    : "bg-stone-100 border-ink/15 text-ink-500 hover:bg-bone-200 hover:text-steel-900"
                }`}
                title={`${combo.state} · ${formatPermitType(combo.type)} — ${combo.count} permits`}
              >
                <span className="font-bold">{combo.state}</span>
                <span className="opacity-80">{formatPermitType(combo.type)}</span>
                <span className={`text-[9px] rounded px-1 ${active ? "bg-amber/25 text-amber-600" : "bg-bone-200 text-ink-400"}`}>
                  {combo.count}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* Filter pills */}
      <div className="flex items-center gap-2 px-[18px] py-3 border-b border-ink/15">
        {STATUS_FILTERS.map((f) => {
          const isActive = statusFilter === f;
          const colorMap = {
            all:     isActive ? "bg-steel-900 text-white border-steel-900"     : "bg-white border-steel/20 text-steel-900 hover:bg-stone-100",
            Active:  isActive ? "bg-green-600 text-white border-green-600"     : "bg-green-50 border-green-300 text-green-800 hover:bg-green-100",
            Expired: isActive ? "bg-red-600 text-white border-red-600"         : "bg-red-50 border-red-300 text-red-800 hover:bg-red-100",
            Pending: isActive ? "bg-yellow-500 text-white border-yellow-500"   : "bg-yellow-50 border-yellow-300 text-yellow-800 hover:bg-yellow-100",
          };
          return (
            <button
              key={f}
              onClick={() => setStatusFilter(f)}
              className={`px-4 py-2 rounded-sm text-[10px] cursor-pointer transition-colors border uppercase tracking-[0.08em] font-semibold ${colorMap[f]}`}
            >
              {f === "all" ? "All" : f}
            </button>
          );
        })}
        {hasActiveFilters && (
          <button
            onClick={clearAllFilters}
            className="text-[11px] text-ink-400 hover:text-[#7A2C22] bg-transparent border-none cursor-pointer transition-colors font-sans"
          >
            × Clear filters
          </button>
        )}
        <button
          onClick={load}
          className="ml-auto text-xs text-ink-400 hover:text-amber-600 transition-colors cursor-pointer bg-transparent border-none font-sans"
        >
          ↻ Refresh
        </button>
      </div>

      {/* Selection mode banner — visible whenever the user is picking permits */}
      {selectMode && (
        <div className="flex items-center gap-3 px-[18px] py-2.5 bg-amber/10 border-b border-amber/30">
          <span className="text-[12px] text-amber-600 font-medium">
            {selectedIds.size === 0
              ? "Tap permits below to select them for duplication"
              : `${selectedIds.size} selected`}
          </span>
          {selectedIds.size > 0 && (
            <>
              <button
                onClick={duplicateSelectedToCart}
                className="bg-amber text-white border-none px-3 py-[5px] rounded-sm text-[11px] font-medium cursor-pointer hover:bg-amber-600 transition-all font-sans"
              >
                ⧉ Add to Cart & Order
              </button>
              <button
                onClick={clearSelection}
                className="text-[11px] text-ink-400 hover:text-steel-900 bg-transparent border-none cursor-pointer transition-colors font-sans"
              >
                Clear selection
              </button>
            </>
          )}
          <button
            onClick={exitSelectMode}
            className="ml-auto text-[11px] text-ink-400 hover:text-steel-900 bg-transparent border-none cursor-pointer transition-colors font-sans"
          >
            Exit
          </button>
        </div>
      )}

      {loading ? (
        <div className="p-10 text-center text-ink-400 text-[13px]">Loading...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-10 text-ink-400 text-[13px]">
          <div className="text-[32px] mb-2.5">📋</div>
          No permits match this filter.
        </div>
      ) : (
        <table className="w-full border-collapse">
          <thead>
            <tr className="text-[11px] text-ink-400 font-medium uppercase tracking-wide bg-stone-100">
              {selectMode && (
                <th className="py-2.5 px-3 border-b border-ink/15 w-[36px] text-center">
                  <input
                    type="checkbox"
                    checked={filtered.length > 0 && filtered.every((p) => selectedIds.has(p.id))}
                    onChange={toggleSelectAllVisible}
                    className="!w-auto !m-0 cursor-pointer accent-amber"
                    title="Select all visible"
                  />
                </th>
              )}
              <th className="text-left py-2.5 px-3.5 border-b border-ink/15 w-[80px]">Permit #</th>
              <th className="text-left py-2.5 px-3.5 border-b border-ink/15">Driver</th>
              <th className="text-left py-2.5 px-3.5 border-b border-ink/15 w-[90px]">Tractor</th>
              <th className="text-left py-2.5 px-3.5 border-b border-ink/15 w-[60px]">State</th>
              <th className="text-left py-2.5 px-3.5 border-b border-ink/15 w-[140px]">Type</th>
              <th className="text-left py-2.5 px-3.5 border-b border-ink/15 w-[110px]">Effective</th>
              <th className="text-left py-2.5 px-3.5 border-b border-ink/15 w-[110px]">Expires</th>
              <th className="text-left py-2.5 px-3.5 border-b border-ink/15 w-[90px]">Status</th>
              <th className="py-2.5 px-3.5 border-b border-ink/15 w-[70px]"></th>
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
                      ? `cursor-pointer ${checked ? "bg-amber/10" : "hover:bg-stone-100"}`
                      : "hover:bg-stone-100"
                  }`}
                >
                  {selectMode && (
                    <td className="py-2.5 px-3 border-b border-ink/15 text-center">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleSelect(p.id)}
                        onClick={(e) => e.stopPropagation()}
                        className="!w-auto !m-0 cursor-pointer accent-amber"
                      />
                    </td>
                  )}
                  <td className="py-2.5 px-3.5 border-b border-ink/15 font-mono text-xs text-ink-400">{p.id}</td>
                  <td className="py-2.5 px-3.5 border-b border-ink/15">
                    <div className="flex items-center gap-[7px]">
                      <div className="w-6 h-6 rounded-full bg-stone-100 border border-ink/15 flex items-center justify-center text-[9px] font-semibold text-amber-600 flex-shrink-0">
                        {initials}
                      </div>
                      <span className="text-[13px]">{p.driverName || "—"}</span>
                    </div>
                  </td>
                  <td className="py-2.5 px-3.5 border-b border-ink/15 font-mono text-[12px] text-ink-500">
                    {p.tractor || "—"}
                  </td>
                  <td className="py-2.5 px-3.5 border-b border-ink/15">
                    <span className="text-[11px] font-bold text-amber-600 px-2 py-1 bg-amber/10 border border-amber/30 rounded-sm">
                      {p.state || "—"}
                    </span>
                  </td>
                  <td className="py-2.5 px-3.5 border-b border-ink/15 text-[12.5px] text-steel-900">
                    {formatPermitType(p.type)}
                  </td>
                  <td className="py-2.5 px-3.5 border-b border-ink/15 text-[13px] text-ink-500">{p.effDate || "—"}</td>
                  <td className="py-2.5 px-3.5 border-b border-ink/15 text-[13px] text-ink-500">{p.expDate || "—"}</td>
                  <td className="py-2.5 px-3.5 border-b border-ink/15"><Badge type={p.status} /></td>
                  <td className="py-2.5 px-3.5 border-b border-ink/15">
                    <button className="bg-stone-100 border border-ink/15 text-ink-500 rounded-sm px-2.5 py-1 text-[11px] cursor-pointer hover:bg-bone-200 hover:text-amber-600 hover:border-amber/40 transition-all inline-flex items-center gap-1 font-sans">
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
