import { useState, useEffect } from "react";
import { fetchBlanketPermits } from "../api";
import Badge from "./Badge";

export default function BlanketPermits({ onToast }) {
  const [blankets, setBlankets] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchBlanketPermits().then((data) => {
      setBlankets(data);
      setLoading(false);
    });
  }, []);

  function daysUntil(expStr) {
    const parts = expStr.split("/");
    const expDate = new Date(parseInt(parts[2]), parseInt(parts[0]) - 1, parseInt(parts[1]));
    return Math.round((expDate - new Date()) / 86400000);
  }

  return (
    <div className="bg-white border border-ink/15">
      <div className="px-[18px] py-3.5 border-b border-ink/15 flex items-center gap-2.5">
        <div className="text-[13.5px] font-semibold">Blanket Permits on File</div>
        <div className="ml-auto">
          <button
            onClick={() => onToast?.("ℹ", "Add blanket permit feature coming soon")}
            className="bg-amber text-white border-none px-3 py-1.5 rounded-sm text-xs font-medium cursor-pointer hover:bg-amber-600 transition-all font-sans"
          >
            + Add Blanket
          </button>
        </div>
      </div>

      {loading ? (
        <div className="p-10 text-center text-ink-400 text-[13px]">Loading...</div>
      ) : blankets.length === 0 ? (
        <div className="text-center py-10 text-ink-400 text-[13px]">
          <div className="text-[32px] mb-2.5">📄</div>
          No blanket permits on file.
        </div>
      ) : (
        <div>
          {blankets.map((b) => {
            const days = daysUntil(b.exp);
            return (
              <div key={b.id} className="flex items-center gap-2.5 px-[18px] py-3 border-b border-ink/15 last:border-b-0">
                <div className="w-9 h-9 rounded-sm bg-bone-3 flex items-center justify-center text-[11px] font-bold text-amber-600 tracking-wide flex-shrink-0">
                  {b.state}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[12.5px] font-medium">{b.driverName}</div>
                  <div className="text-[11px] text-ink-400 mt-px">Permit #{b.num} · Expires {b.exp}</div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge type={days < 30 ? "Pending" : "Active"} />
                  <button
                    onClick={() => onToast?.("↓", "Downloading blanket permit PDF...")}
                    className="bg-bone-3 border border-ink/15 text-ink-500 rounded-sm px-2.5 py-1 text-[11px] cursor-pointer hover:bg-bone-4 hover:text-amber-600 hover:border-amber/40 transition-all inline-flex items-center gap-1 font-sans"
                  >
                    ↓ PDF
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
