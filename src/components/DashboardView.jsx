import { useState, useEffect } from "react";
import { fetchPermitHistory, fetchBlanketPermits } from "../api";
import StatCards from "./StatCards";
import Badge from "./Badge";

export default function DashboardView({ onNavigate }) {
  const [history, setHistory] = useState([]);
  const [blankets, setBlankets] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchPermitHistory(), fetchBlanketPermits()])
      .then(([h, b]) => {
        setHistory(Array.isArray(h) ? h : []);
        setBlankets(Array.isArray(b) ? b : []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const recent = [...history].reverse().slice(0, 8);

  function daysUntil(expStr) {
    if (!expStr) return 999;
    let expDate;
    if (expStr.includes("/")) {
      const [m, d, y] = expStr.split("/");
      expDate = new Date(parseInt(y), parseInt(m) - 1, parseInt(d));
    } else {
      expDate = new Date(expStr);
    }
    if (isNaN(expDate)) return 999;
    return Math.round((expDate - new Date()) / 86400000);
  }

  return (
    <div>
      <StatCards history={history} blanketCount={blankets.length} />

      {/* Quick actions row */}
      <div className="flex items-center gap-3 mb-8">
        <button
          onClick={() => onNavigate("order")}
          className="bg-amber text-white border-none px-6 py-3 rounded-sm text-[11px] font-semibold uppercase tracking-[0.06em] cursor-pointer hover:bg-amber-600 transition-colors"
        >
          + Order New Permit
        </button>
        <button
          onClick={() => onNavigate("blankets")}
          className="bg-white border border-steel/20 text-steel-900 px-5 py-3 rounded-sm text-[11px] font-semibold uppercase tracking-[0.06em] cursor-pointer hover:bg-stone-100 transition-colors"
        >
          Manage Blankets
        </button>
        <button
          onClick={() => onNavigate("drivers")}
          className="bg-white border border-steel/20 text-steel-900 px-5 py-3 rounded-sm text-[11px] font-semibold uppercase tracking-[0.06em] cursor-pointer hover:bg-stone-100 transition-colors"
        >
          Driver Database
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Recent Permits */}
        <div className="lg:col-span-8 border border-ink/15 bg-white">
          <div className="px-6 py-4 border-b border-ink/15 flex items-center justify-between">
            <span className="text-[14px] font-semibold text-steel-900">Recent Permits</span>
            <button
              onClick={() => onNavigate("history")}
              className="text-[11px] text-amber-600 font-semibold hover:text-amber cursor-pointer bg-transparent border-none uppercase tracking-[0.06em] transition-colors"
            >
              View all →
            </button>
          </div>
          {loading ? (
            <div className="p-14 text-center text-ink-400 text-sm">Loading…</div>
          ) : recent.length === 0 ? (
            <div className="p-14 text-center text-ink-400 text-sm">No permits filed yet. Click "Order New Permit" to get started.</div>
          ) : (
            <table className="w-full border-collapse">
              <thead>
                <tr className="bg-stone-100">
                  {["ID", "Driver", "Type", "Effective", "Status"].map((h) => (
                    <th key={h} className="text-left py-3 px-5 text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recent.map((p) => {
                  const initials = (p.driverName || "??").split(",")[0].substring(0, 2).toUpperCase();
                  return (
                    <tr key={p.id} className="border-b border-ink/10 hover:bg-amber/[0.03] transition-colors">
                      <td className="py-3 px-5 text-xs text-ink-400 tabular-nums">{p.id}</td>
                      <td className="py-3 px-5">
                        <div className="flex items-center gap-2.5">
                          <div className="w-7 h-7 rounded-sm bg-stone-100 border border-ink/10 flex items-center justify-center text-[10px] font-semibold text-steel-900">
                            {initials}
                          </div>
                          <span className="text-[13px] text-steel-900 font-medium">{p.driverName}</span>
                        </div>
                      </td>
                      <td className="py-3 px-5"><Badge type={p.type} /></td>
                      <td className="py-3 px-5 text-[13px] text-ink-500">{p.effDate}</td>
                      <td className="py-3 px-5"><Badge type={p.status} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Right column */}
        <div className="lg:col-span-4 space-y-6">
          {/* Blanket Permits */}
          <div className="border border-ink/15 bg-white">
            <div className="px-6 py-4 border-b border-ink/15 flex items-center justify-between">
              <span className="text-[14px] font-semibold text-steel-900">Blanket Permits</span>
              <span className="text-[11px] text-ink-400 font-medium">{blankets.length} on file</span>
            </div>
            {blankets.length === 0 ? (
              <div className="p-10 text-center text-ink-400 text-[12px]">None on file.</div>
            ) : (
              <div>
                {blankets.slice(0, 5).map((b) => {
                  const days = daysUntil(b.exp);
                  return (
                    <div key={b.id} className="flex items-center gap-3 px-6 py-3.5 border-b border-ink/10 last:border-b-0">
                      <span className="text-[11px] font-bold text-amber-600 bg-amber/10 border border-amber/30 rounded-sm px-2 py-1 tracking-wider flex-shrink-0">
                        {b.state}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="text-[12px] font-medium text-steel-900 truncate">{b.driverName}</div>
                        <div className="text-[10px] text-ink-400">Exp {b.exp}</div>
                      </div>
                      <Badge type={days < 30 ? "Pending" : "Active"} />
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Summary */}
          <div className="border border-ink/15 bg-white">
            <div className="px-6 py-4 border-b border-ink/15">
              <span className="text-[14px] font-semibold text-steel-900">Summary</span>
            </div>
            <div className="px-6 py-5 space-y-4 text-[13px]">
              <div className="flex items-center justify-between">
                <span className="text-ink-500">States covered</span>
                <span className="font-semibold text-steel-900 tabular-nums">
                  {new Set(history.map((p) => p.state).filter(Boolean)).size || "—"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-500">Total permits filed</span>
                <span className="font-semibold text-steel-900 tabular-nums">{history.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-500">Blankets on file</span>
                <span className="font-semibold text-steel-900 tabular-nums">{blankets.length}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
