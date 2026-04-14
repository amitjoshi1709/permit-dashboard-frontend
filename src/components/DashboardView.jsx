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

      <div className="grid grid-cols-[1fr_340px] gap-[18px]">
        {/* Recent Permits */}
        <div className="bg-navy-2 border border-subtle rounded-[14px]">
          <div className="px-[18px] py-3.5 border-b border-subtle flex items-center gap-2.5">
            <div className="text-[13.5px] font-semibold">Recent Permits</div>
            <span className="text-[11px] text-txt-3 bg-navy-3 rounded-[10px] px-2 py-0.5">Last {recent.length}</span>
            <div className="ml-auto">
              <button
                onClick={() => onNavigate("history")}
                className="bg-transparent border border-subtle2 text-txt-2 rounded-md px-2.5 py-1 text-xs cursor-pointer hover:bg-navy-3 hover:text-txt-1 transition-all font-sans"
              >
                View all
              </button>
            </div>
          </div>
          {loading ? (
            <div className="p-10 text-center text-txt-3 text-[13px]">Loading...</div>
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
                {recent.map((p) => {
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

        {/* Right column */}
        <div className="space-y-3.5">
          {/* Blanket Permits mini */}
          <div className="bg-navy-2 border border-subtle rounded-[14px]">
            <div className="px-[18px] py-3.5 border-b border-subtle">
              <div className="text-[13.5px] font-semibold">Blanket Permits on File</div>
            </div>
            <div className="py-2.5">
              {blankets.slice(0, 4).map((b) => {
                const days = daysUntil(b.exp);
                return (
                  <div key={b.id} className="flex items-center gap-2.5 px-[18px] py-2.5 border-b border-subtle last:border-b-0">
                    <div className="w-9 h-9 rounded-lg bg-navy-3 flex items-center justify-center text-[11px] font-bold text-accent-2 tracking-wide flex-shrink-0">
                      {b.state}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-[12.5px] font-medium truncate">{b.driverName.split(" ")[0]} {b.driverName.split(" ")[1]}</div>
                      <div className="text-[11px] text-txt-3 mt-px">Expires {b.exp} · #{b.num}</div>
                    </div>
                    <Badge type={days < 30 ? "Pending" : "Active"} />
                  </div>
                );
              })}
              {blankets.length > 4 && (
                <div
                  onClick={() => onNavigate("blankets")}
                  className="py-2.5 px-[18px] text-xs text-txt-3 text-center cursor-pointer hover:text-txt-2"
                >
                  View {blankets.length - 4} more →
                </div>
              )}
            </div>
          </div>

          {/* Quick Actions */}
          <div className="bg-navy-2 border border-subtle rounded-[14px]">
            <div className="px-[18px] py-3.5 border-b border-subtle">
              <div className="text-[13.5px] font-semibold">Quick Actions</div>
            </div>
            <div className="p-3.5 space-y-2">
              <button
                onClick={() => onNavigate("order")}
                className="w-full bg-accent text-white border-none py-2 rounded-lg text-[13px] font-medium cursor-pointer hover:bg-accent-2 transition-all font-sans"
              >
                + Order New Permit
              </button>
              <button
                onClick={() => onNavigate("blankets")}
                className="w-full bg-transparent border border-subtle2 text-txt-2 py-2 rounded-lg text-[13px] cursor-pointer hover:bg-navy-3 hover:text-txt-1 transition-all font-sans"
              >
                Manage Blanket Permits
              </button>
              <button
                onClick={() => onNavigate("settings")}
                className="w-full bg-transparent border border-subtle2 text-txt-2 py-2 rounded-lg text-[13px] cursor-pointer hover:bg-navy-3 hover:text-txt-1 transition-all font-sans"
              >
                Update Credit Card
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
