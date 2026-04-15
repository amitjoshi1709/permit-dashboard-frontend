import Badge from "./Badge";

// Lower number = higher in the list. Currently-running permits surface at the
// very top so the user always sees what's active right now.
const STATUS_ORDER = {
  processing: 0, // the one being worked on right now
  pending: 1,    // queued, waiting for its turn
  error: 2,
  success: 3,
};

const isActiveStatus = (s) => s !== "success" && s !== "error" && s !== "pending";

export default function JobTracker({ jobs, onClear }) {
  const allPermits = (jobs || []).flatMap((j) =>
    (j.permits || []).map((p) => ({ ...p, state: p.state || j.state }))
  );

  const total = allPermits.length;
  const completed = allPermits.filter((p) => p.status === "success").length;
  const failed = allPermits.filter((p) => p.status === "error").length;
  const queued = allPermits.filter((p) => p.status === "pending").length;
  const inProgress = total - completed - failed - queued;
  const allDone = total > 0 && queued === 0 && inProgress === 0;

  // Sort: running first (top), then queued, then errors, then success.
  // Any permit whose status is NOT pending/success/error is treated as "running".
  const statusRank = (s) => {
    if (isActiveStatus(s)) return STATUS_ORDER.processing;
    return STATUS_ORDER[s] ?? STATUS_ORDER.processing;
  };
  const sorted = [...allPermits].sort((a, b) => statusRank(a.status) - statusRank(b.status));

  const pctDone = total > 0 ? Math.round(((completed + failed) / total) * 100) : 0;

  function handleClear() {
    onClear?.();
  }

  return (
    <div className="bg-navy/80 border border-subtle rounded-lg overflow-hidden">
      {/* Header */}
      <div className="px-3.5 py-2.5 border-b border-subtle">
        <div className="flex items-center justify-between mb-1.5">
          <span className="font-semibold text-txt-1 text-[12px]">
            {total === 0 ? "Order History"
              : allDone ? "Order Complete"
              : "Order Status"}
          </span>
          <div className="flex items-center gap-2.5">
            {total > 0 && (
              <span className="text-[11px] text-txt-3">
                {completed + failed} / {total} done
              </span>
            )}
            {total > 0 && onClear && (
              <button
                onClick={handleClear}
                className="text-[11px] text-txt-3 hover:text-permit-red2 cursor-pointer bg-transparent border-none font-sans transition-colors"
              >
                Clear history
              </button>
            )}
          </div>
        </div>

        {/* Progress bar */}
        <div className="w-full h-1.5 bg-navy-3 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${pctDone}%`,
              background: failed > 0 ? "linear-gradient(90deg, #3EDB7A, #E74C3C)" : "#3EDB7A",
            }}
          />
        </div>

        {/* Counts */}
        {total > 0 && (
          <div className="flex gap-3 mt-1.5 text-[10px]">
            {queued > 0 && <span className="text-txt-3">{queued} queued</span>}
            {inProgress > 0 && <span className="text-accent-2">{inProgress} running</span>}
            {completed > 0 && <span className="text-[#3EDB7A]">{completed} completed</span>}
            {failed > 0 && <span className="text-permit-red2">{failed} failed</span>}
          </div>
        )}
      </div>

      {/* Permit list — empty state if nothing yet */}
      {total === 0 ? (
        <div className="py-6 text-center text-txt-3 text-[12px]">
          No permits ordered yet. Your order history will appear here.
        </div>
      ) : (
        <div className="max-h-96 overflow-y-auto divide-y divide-subtle/40">
          {sorted.map((p, i) => (
            <div
              key={p.permitId || `p-${i}`}
              className={`flex items-center gap-2 px-3.5 py-2.5 text-[12px] transition-colors ${
                p.status === "success"
                  ? "bg-[#3EDB7A]/5"
                  : p.status === "error"
                  ? "bg-permit-red2/5"
                  : p.status === "pending"
                  ? "opacity-60"
                  : ""
              }`}
            >
              {/* Status indicator */}
              <div className="flex-shrink-0 w-5 text-center text-[13px]">
                {p.status === "success" ? (
                  <span className="text-[#3EDB7A]">✓</span>
                ) : p.status === "error" ? (
                  <span className="text-permit-red2">✗</span>
                ) : p.status === "pending" ? (
                  <span className="text-txt-3">○</span>
                ) : (
                  <span className="text-accent-2 animate-pulse">◉</span>
                )}
              </div>

              {/* Driver avatar */}
              <div className="w-5 h-5 rounded-full bg-steel flex items-center justify-center text-[8px] font-semibold text-accent-2 flex-shrink-0">
                {(p.driverName || "??").substring(0, 2).toUpperCase()}
              </div>

              {/* Driver name + tractor */}
              <div className="flex-1 min-w-0">
                <div className="text-txt-1 truncate">
                  {p.driverName || "—"}
                  {p.tractor && (
                    <span className="text-txt-3 ml-1.5 font-mono text-[10px]">{p.tractor}</span>
                  )}
                </div>
                {p.status === "error" && p.message && (
                  <div className="text-[10px] text-permit-red2 truncate" title={p.message}>
                    {p.message}
                  </div>
                )}
              </div>

              {/* State */}
              <span className="text-[10px] font-bold text-accent px-1.5 py-0.5 bg-accent/10 rounded flex-shrink-0">
                {p.state || "—"}
              </span>

              {/* Permit type */}
              <div className="flex-shrink-0">
                <Badge type={p.permitType || ""} />
              </div>

              {/* Status + time */}
              <span className={`text-[10px] flex-shrink-0 text-right ${
                p.status === "success" ? "text-[#3EDB7A]"
                  : p.status === "error" ? "text-permit-red2"
                  : p.status === "pending" ? "text-txt-3"
                  : "text-accent-2"
              }`}>
                {p.status === "success" ? (p.finishedAt || "Done")
                  : p.status === "error" ? (p.finishedAt ? `Failed ${p.finishedAt}` : "Failed")
                  : p.status === "pending" ? "Queued"
                  : "Running"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
