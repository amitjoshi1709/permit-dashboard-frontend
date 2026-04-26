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
    <div className="bg-white border border-ink/15 rounded-sm overflow-hidden">
      {/* Header */}
      <div className="px-3.5 py-2.5 border-b border-ink/15">
        <div className="flex items-center justify-between mb-1.5">
          <span className="font-semibold text-steel-900 text-[12px]">
            {total === 0 ? "Order History"
              : allDone ? "Order Complete"
              : "Order Status"}
          </span>
          <div className="flex items-center gap-2.5">
            {total > 0 && (
              <span className="text-[11px] text-ink-400">
                {completed + failed} / {total} done
              </span>
            )}
            {total > 0 && onClear && (
              <button
                onClick={handleClear}
                className="text-[11px] text-ink-400 hover:text-[#7A2C22] cursor-pointer bg-transparent border-none font-sans transition-colors"
              >
                Clear history
              </button>
            )}
          </div>
        </div>

        {/* Progress bar */}
        <div className="w-full h-1.5 bg-bone-3 rounded-full overflow-hidden">
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
            {queued > 0 && <span className="text-ink-400">{queued} queued</span>}
            {inProgress > 0 && <span className="text-amber-600">{inProgress} running</span>}
            {completed > 0 && <span className="text-[#2E6A3B]">{completed} completed</span>}
            {failed > 0 && <span className="text-[#7A2C22]">{failed} failed</span>}
          </div>
        )}
      </div>

      {/* Permit list — empty state if nothing yet */}
      {total === 0 ? (
        <div className="py-6 text-center text-ink-400 text-[12px]">
          No permits ordered yet. Your order history will appear here.
        </div>
      ) : (
        <div className="max-h-96 overflow-y-auto divide-y divide-ink/10">
          {sorted.map((p, i) => (
            <div
              key={p.permitId || `p-${i}`}
              className={`flex items-center gap-2 px-3.5 py-2.5 text-[12px] transition-colors ${
                p.status === "success"
                  ? "bg-[#2E6A3B]/[0.05]"
                  : p.status === "error"
                  ? "bg-[#9C3A2E]/[0.04]"
                  : p.status === "pending"
                  ? "opacity-60"
                  : ""
              }`}
            >
              {/* Status indicator */}
              <div className="flex-shrink-0 w-5 text-center text-[13px]">
                {p.status === "success" ? (
                  <span className="text-[#2E6A3B]">✓</span>
                ) : p.status === "error" ? (
                  <span className="text-[#7A2C22]">✗</span>
                ) : p.status === "pending" ? (
                  <span className="text-ink-400">○</span>
                ) : (
                  <span className="text-amber-600 animate-pulse">◉</span>
                )}
              </div>

              {/* Driver avatar */}
              <div className="w-5 h-5 rounded-full bg-stone-100 border border-ink/15 flex items-center justify-center text-[8px] font-semibold text-amber-600 flex-shrink-0">
                {(p.driverName || "??").substring(0, 2).toUpperCase()}
              </div>

              {/* Driver name + tractor */}
              <div className="flex-1 min-w-0">
                <div className="text-steel-900 truncate">
                  {p.driverName || "—"}
                  {p.tractor && (
                    <span className="text-ink-400 ml-1.5 font-mono text-[10px]">{p.tractor}</span>
                  )}
                </div>
                {p.status === "error" && p.message && (
                  <div className="text-[10px] text-[#7A2C22] truncate" title={p.message}>
                    {p.message}
                  </div>
                )}
              </div>

              {/* State */}
              <span className="text-[10px] font-bold text-amber-600 px-1.5 py-0.5 bg-amber/10 rounded flex-shrink-0">
                {p.state || "—"}
              </span>

              {/* Permit type */}
              <div className="flex-shrink-0">
                <Badge type={p.permitType || ""} />
              </div>

              {/* Status + time */}
              <span className={`text-[10px] flex-shrink-0 text-right ${
                p.status === "success" ? "text-[#2E6A3B]"
                  : p.status === "error" ? "text-[#7A2C22]"
                  : p.status === "pending" ? "text-ink-400"
                  : "text-amber-600"
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
