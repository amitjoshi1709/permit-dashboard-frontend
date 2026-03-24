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
    <div className="bg-navy-2 border border-subtle rounded-[14px]">
      <div className="px-[18px] py-3.5 border-b border-subtle flex items-center gap-2.5">
        <div className="text-[13.5px] font-semibold">Blanket Permits on File</div>
        <div className="ml-auto">
          <button
            onClick={() => onToast?.("ℹ", "Add blanket permit feature coming soon")}
            className="bg-accent text-white border-none px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer hover:bg-accent-2 transition-all font-sans"
          >
            + Add Blanket
          </button>
        </div>
      </div>

      {loading ? (
        <div className="p-10 text-center text-txt-3 text-[13px]">Loading...</div>
      ) : blankets.length === 0 ? (
        <div className="text-center py-10 text-txt-3 text-[13px]">
          <div className="text-[32px] mb-2.5">📄</div>
          No blanket permits on file.
        </div>
      ) : (
        <div>
          {blankets.map((b) => {
            const days = daysUntil(b.exp);
            return (
              <div key={b.id} className="flex items-center gap-2.5 px-[18px] py-3 border-b border-subtle last:border-b-0">
                <div className="w-9 h-9 rounded-lg bg-navy-3 flex items-center justify-center text-[11px] font-bold text-accent-2 tracking-wide flex-shrink-0">
                  {b.state}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[12.5px] font-medium">{b.driverName}</div>
                  <div className="text-[11px] text-txt-3 mt-px">Permit #{b.num} · Expires {b.exp}</div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge type={days < 30 ? "Pending" : "Active"} />
                  <button
                    onClick={() => onToast?.("↓", "Downloading blanket permit PDF...")}
                    className="bg-navy-3 border border-subtle text-txt-2 rounded-md px-2.5 py-1 text-[11px] cursor-pointer hover:bg-navy-4 hover:text-accent-2 hover:border-accent transition-all inline-flex items-center gap-1 font-sans"
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
