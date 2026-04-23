import { useState, useEffect } from "react";
import { fetchBlanketPermits } from "../api";
import Badge from "./Badge";

const PERMIT_TYPE_LABELS = {
  fl_blanket_bulk: "FL Blanket — Bulk",
  fl_blanket_inner_bridge: "FL Blanket — Inner Bridge",
  fl_blanket_flatbed: "FL Blanket — Flatbed",
};

function formatType(type) {
  return PERMIT_TYPE_LABELS[type] || type || "—";
}

function daysUntil(expStr) {
  if (!expStr) return null;
  const parts = expStr.split("/");
  if (parts.length !== 3) return null;
  const expDate = new Date(parseInt(parts[2]), parseInt(parts[0]) - 1, parseInt(parts[1]));
  return Math.round((expDate - new Date()) / 86400000);
}

const PENDING_CART_KEY = "permitflow_pending_cart";

export default function BlanketPermits({ onToast, onNavigate }) {
  const [blankets, setBlankets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [driverSearch, setDriverSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());

  function load() {
    setLoading(true);
    fetchBlanketPermits()
      .then((data) => {
        setBlankets(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(() => {
        setBlankets([]);
        setLoading(false);
      });
  }

  useEffect(() => { load(); }, []);

  function toggleSelect(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    const visibleIds = filtered.map((b) => b.id);
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

  function renewSelected() {
    const picks = blankets.filter((b) => selectedIds.has(b.id));
    if (picks.length === 0) return;
    const payload = picks.map((b) => ({
      driverId: b.driverId ?? null,
      driverName: b.driverName || "",
      tractor: b.tractor || "",
      state: b.state || "",
      type: b.type || "",
      sourceId: b.id,
      extraFields: b.extraFields || null,
    }));
    try {
      localStorage.setItem(PENDING_CART_KEY, JSON.stringify(payload));
    } catch {}
    onToast?.("✓", `${picks.length} blanket permit${picks.length > 1 ? "s" : ""} staged for renewal`);
    setSelectMode(false);
    setSelectedIds(new Set());
    onNavigate?.("order");
  }

  const uniqueTypes = Array.from(new Set(blankets.map((b) => b.type).filter(Boolean)));

  let filtered = [...blankets];
  if (typeFilter !== "all") filtered = filtered.filter((b) => b.type === typeFilter);
  if (statusFilter !== "all") filtered = filtered.filter((b) => b.status === statusFilter);
  if (driverSearch.trim()) {
    const q = driverSearch.trim().toLowerCase();
    filtered = filtered.filter((b) => {
      const name = (b.driverName || "").toLowerCase();
      const tractor = (b.tractor || "").toLowerCase();
      return name.includes(q) || tractor.includes(q);
    });
  }

  const active = filtered.filter((b) => b.status === "Active");
  const expiring = filtered.filter((b) => b.status === "Expiring Soon");
  const expired = filtered.filter((b) => b.status === "Expired");

  return (
    <div className="bg-white border border-ink/15">
      <div className="px-[18px] py-3.5 border-b border-ink/15 flex items-center gap-2.5">
        <div className="text-[13.5px] font-semibold">Blanket Permits on File</div>
        <span className="text-[11px] text-ink-400 bg-bone-3 rounded-sm px-2 py-0.5">
          {filtered.length}{filtered.length !== blankets.length ? ` / ${blankets.length}` : ""} {filtered.length === 1 ? "permit" : "permits"}
        </span>
        {!selectMode ? (
          <button
            onClick={() => { setSelectMode(true); setSelectedIds(new Set()); }}
            className="ml-2 inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-sm text-[12px] font-semibold cursor-pointer bg-white border-2 border-amber text-amber-600 hover:bg-amber hover:text-white transition-all font-sans"
          >
            ↻ Renew Permits
          </button>
        ) : (
          <button
            onClick={() => { setSelectMode(false); setSelectedIds(new Set()); }}
            className="ml-2 inline-flex items-center gap-1 px-2.5 py-1 rounded-sm text-[11px] font-medium cursor-pointer bg-transparent border border-ink/15 text-ink-400 hover:text-steel-900 transition-all font-sans"
          >
            Cancel
          </button>
        )}
        <div className="ml-auto flex gap-2">
          <div className="relative">
            <input
              type="text"
              value={driverSearch}
              onChange={(e) => setDriverSearch(e.target.value)}
              placeholder="Search driver or tractor..."
              className="!w-[180px] !py-1.5 !px-2.5 !text-xs"
            />
            {driverSearch && (
              <button
                onClick={() => setDriverSearch("")}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 text-ink-400 hover:text-steel-900 bg-transparent border-none cursor-pointer text-sm leading-none"
              >
                ×
              </button>
            )}
          </div>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="!w-auto !py-1.5 !px-2.5 !text-xs"
          >
            <option value="all">All Types</option>
            {uniqueTypes.map((t) => (
              <option key={t} value={t}>{formatType(t)}</option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="!w-auto !py-1.5 !px-2.5 !text-xs"
          >
            <option value="all">All Status</option>
            <option value="Active">Active</option>
            <option value="Expiring Soon">Expiring Soon</option>
            <option value="Expired">Expired</option>
          </select>
          <button
            onClick={load}
            className="text-xs text-ink-400 hover:text-amber-600 transition-colors cursor-pointer bg-transparent border-none font-sans"
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Summary cards */}
      {blankets.length > 0 && (
        <div className="grid grid-cols-3 gap-3 px-[18px] py-3.5 border-b border-ink/15">
          <div className="bg-[#2E6A3B]/5 border border-[#2E6A3B]/20 rounded-sm px-3 py-2 text-center">
            <div className="text-[18px] font-semibold text-[#2E6A3B]">{active.length}</div>
            <div className="text-[10px] text-ink-400 uppercase tracking-wide">Active</div>
          </div>
          <div className="bg-amber/5 border border-amber/20 rounded-sm px-3 py-2 text-center">
            <div className="text-[18px] font-semibold text-amber-600">{expiring.length}</div>
            <div className="text-[10px] text-ink-400 uppercase tracking-wide">Expiring Soon</div>
          </div>
          <div className="bg-[#7A2C22]/5 border border-[#7A2C22]/20 rounded-sm px-3 py-2 text-center">
            <div className="text-[18px] font-semibold text-[#7A2C22]">{expired.length}</div>
            <div className="text-[10px] text-ink-400 uppercase tracking-wide">Expired</div>
          </div>
        </div>
      )}

      {/* Selection mode banner */}
      {selectMode && (
        <div className="flex items-center gap-3 px-[18px] py-2.5 bg-amber/10 border-b border-amber/30">
          <input
            type="checkbox"
            checked={filtered.length > 0 && filtered.every((b) => selectedIds.has(b.id))}
            onChange={toggleSelectAll}
            className="!w-auto !m-0 cursor-pointer accent-amber"
            title="Select all visible"
          />
          <span className="text-[12px] text-amber-600 font-medium">
            {selectedIds.size === 0
              ? "Select permits to renew"
              : `${selectedIds.size} selected`}
          </span>
          {selectedIds.size > 0 && (
            <>
              <button
                onClick={renewSelected}
                className="bg-amber text-white border-none px-3 py-[5px] rounded-sm text-[11px] font-medium cursor-pointer hover:bg-amber-600 transition-all font-sans"
              >
                ⧉ Add to Cart & Renew
              </button>
              <button
                onClick={() => setSelectedIds(new Set())}
                className="text-[11px] text-ink-400 hover:text-steel-900 bg-transparent border-none cursor-pointer transition-colors font-sans"
              >
                Clear selection
              </button>
            </>
          )}
          <button
            onClick={() => { setSelectMode(false); setSelectedIds(new Set()); }}
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
          <div className="text-[32px] mb-2.5">{blankets.length === 0 ? "📄" : "🔍"}</div>
          <div>{blankets.length === 0 ? "No blanket permits on file." : "No blanket permits match your filters."}</div>
          {blankets.length === 0 && (
            <div className="text-[11px] mt-1 opacity-60">Order a FL blanket permit and it will appear here automatically.</div>
          )}
        </div>
      ) : (
        <div>
          {filtered.map((b) => {
            const days = daysUntil(b.expDate);
            const statusColor =
              b.status === "Expired" ? "text-[#7A2C22]"
              : b.status === "Expiring Soon" ? "text-amber-600"
              : "text-[#2E6A3B]";

            const checked = selectedIds.has(b.id);
            return (
              <div
                key={b.id}
                onClick={selectMode ? () => toggleSelect(b.id) : undefined}
                className={`flex items-center gap-2.5 px-[18px] py-3 border-b border-ink/15 last:border-b-0 transition-colors ${
                  selectMode
                    ? `cursor-pointer ${checked ? "bg-amber/10" : "hover:bg-bone-3"}`
                    : ""
                }`}
              >
                {selectMode && (
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleSelect(b.id)}
                    onClick={(e) => e.stopPropagation()}
                    className="!w-auto !m-0 cursor-pointer accent-amber flex-shrink-0"
                  />
                )}
                <div className="w-9 h-9 rounded-sm bg-bone-3 flex items-center justify-center text-[11px] font-bold text-amber-600 tracking-wide flex-shrink-0">
                  {b.state}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[12.5px] font-medium">{b.driverName || "—"}</div>
                  <div className="text-[11px] text-ink-400 mt-px">
                    {b.id} · {formatType(b.type)}
                    {b.tractor && <span className="font-mono ml-1.5">{b.tractor}</span>}
                  </div>
                </div>
                <div className="text-right flex-shrink-0">
                  <div className="text-[11px] text-ink-400">
                    {b.effDate || "—"} → {b.expDate || "—"}
                  </div>
                  {days !== null && (
                    <div className={`text-[10px] font-medium ${statusColor}`}>
                      {b.status === "Expired"
                        ? `Expired ${Math.abs(days)} days ago`
                        : `${days} days remaining`}
                    </div>
                  )}
                </div>
                <Badge type={b.status} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
