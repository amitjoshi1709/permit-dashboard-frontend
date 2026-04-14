import Badge from "./Badge";

const STATUS_ORDER = { pending: 0, processing: 1, error: 2, success: 3 };

export default function JobTracker({ jobs, onClear }) {
  if (!jobs || jobs.length === 0) return null;

  // Flatten all permits across jobs
  const allPermits = jobs.flatMap((j) =>
    (j.permits || []).map((p) => ({ ...p, state: p.state || j.state }))
  );

  const total = allPermits.length;
  const completed = allPermits.filter((p) => p.status === "success").length;
  const failed = allPermits.filter((p) => p.status === "error").length;
  const queued = allPermits.filter((p) => p.status === "pending").length;
  const inProgress = total - completed - failed - queued;
  const allDone = queued === 0 && inProgress === 0;

  // Sort: in-progress first, then pending, then errors, then success last
  const sorted = [...allPermits].sort(
    (a, b) => (STATUS_ORDER[a.status] ?? 1) - (STATUS_ORDER[b.status] ?? 1)
  );

  // Progress bar
  const pctDone = total > 0 ? Math.round(((completed + failed) / total) * 100) : 0;

  return (
    <div className="bg-navy/80 border border-subtle rounded-lg overflow-hidden">
      {/* Header */}
      <div className="px-3.5 py-2.5 border-b border-subtle">
        <div className="flex items-center justify-between mb-1.5">
          <span className="font-semibold text-txt-1 text-[12px]">
            {allDone ? "Order Complete" : "Order Status"}
          </span>
          <div className="flex items-center gap-2.5">
            <span className="text-[11px] text-txt-3">
              {completed + failed} / {total} done
            </span>
            {allDone && onClear && (
              <button
                onClick={onClear}
                className="text-[11px] text-txt-3 hover:text-txt-1 cursor-pointer bg-transparent border-none font-sans transition-colors"
              >
                Clear
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
        <div className="flex gap-3 mt-1.5 text-[10px]">
          {queued > 0 && <span className="text-txt-3">{queued} queued</span>}
          {inProgress > 0 && <span className="text-accent-2">{inProgress} running</span>}
          {completed > 0 && <span className="text-[#3EDB7A]">{completed} completed</span>}
          {failed > 0 && <span className="text-permit-red2">{failed} failed</span>}
        </div>
      </div>

      {/* Permit list */}
      <div className="max-h-80 overflow-y-auto divide-y divide-subtle/40">
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

            {/* Driver info */}
            <div className="w-5 h-5 rounded-full bg-steel flex items-center justify-center text-[8px] font-semibold text-accent-2 flex-shrink-0">
              {(p.driverName || "??").substring(0, 2).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-txt-1 truncate">
                {p.driverName || "—"}
                {p.tractor && (
                  <span className="text-txt-3 ml-1.5 font-mono text-[10px]">{p.tractor}</span>
                )}
              </div>
              {/* Error message on second line */}
              {p.status === "error" && p.message && (
                <div className="text-[10px] text-permit-red2 truncate" title={p.message}>
                  {p.message}
                </div>
              )}
            </div>

            {/* State badge */}
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
    </div>
  );
}
