import { useState, useEffect } from "react";
import { fetchPermitHistory } from "../api";
import Badge from "./Badge";

const STATUS_FILTERS = ["all", "Active", "Expired", "Pending"];

export default function HistoryTable() {
  const [history, setHistory] = useState([]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    fetchPermitHistory()
      .then((data) => setHistory(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  let filtered = [...history];
  if (typeFilter !== "all") filtered = filtered.filter((p) => p.type === typeFilter);
  if (statusFilter !== "all") filtered = filtered.filter((p) => p.status === statusFilter);

  return (
    <div className="bg-navy-2 border border-subtle rounded-[14px]">
      <div className="px-[18px] py-3.5 border-b border-subtle flex items-center gap-2.5">
        <div className="text-[13.5px] font-semibold">Permit History</div>
        <div className="ml-auto flex gap-2">
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="!w-auto !py-1.5 !px-2.5 !text-xs"
          >
            <option value="all">All Types</option>
            <option value="ITP">Trip (ITP)</option>
            <option value="MFTP">Fuel (MFTP)</option>
          </select>
        </div>
      </div>

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
        <button
          onClick={load}
          className="ml-auto text-xs text-txt-3 hover:text-accent-2 transition-colors cursor-pointer bg-transparent border-none font-sans"
        >
          ↻ Refresh
        </button>
      </div>

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
              <th className="text-left py-2.5 px-3.5 border-b border-subtle">ID</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle">Driver</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle">Type</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle">Effective</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle">Expires</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle">Status</th>
              <th className="py-2.5 px-3.5 border-b border-subtle"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => {
              const initials = (p.driverName || "??").split(",")[0].substring(0, 2).toUpperCase();
              return (
                <tr key={p.id} className="hover:bg-navy-3 transition-colors cursor-pointer">
                  <td className="py-2.5 px-3.5 border-b border-subtle font-mono text-xs text-txt-3">{p.id}</td>
                  <td className="py-2.5 px-3.5 border-b border-subtle">
                    <div className="flex items-center gap-[7px]">
                      <div className="w-6 h-6 rounded-full bg-steel flex items-center justify-center text-[9px] font-semibold text-accent-2 flex-shrink-0">
                        {initials}
                      </div>
                      <span className="text-[13px]">{p.driverName}</span>
                    </div>
                  </td>
                  <td className="py-2.5 px-3.5 border-b border-subtle"><Badge type={p.type} /></td>
                  <td className="py-2.5 px-3.5 border-b border-subtle text-[13px]">{p.effDate}</td>
                  <td className="py-2.5 px-3.5 border-b border-subtle text-[13px]">{p.expDate}</td>
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
