function parseDate(str) {
  if (!str) return null;
  if (str.includes("/")) {
    const [m, d, y] = str.split("/");
    return new Date(parseInt(y), parseInt(m) - 1, parseInt(d));
  }
  return new Date(str);
}

export default function StatCards({ history, blanketCount }) {
  const active = history.filter((p) => p.status === "Active");
  const pending = history.filter((p) => p.status === "Pending");

  const now = new Date();
  const expiringSoon = active.filter((p) => {
    const expDate = parseDate(p.expDate);
    if (!expDate || isNaN(expDate)) return false;
    const diff = Math.round((expDate - now) / 86400000);
    return diff <= 7 && diff >= 0;
  });

  const cards = [
    { label: "Active Permits",   value: active.length,        note: expiringSoon.length > 0 ? `${expiringSoon.length} expiring soon` : "All current", noteColor: expiringSoon.length > 0 ? "text-red-600" : "text-green-700", accent: "border-l-green-500" },
    { label: "Pending Payment",  value: pending.length,       note: pending.length > 0 ? "Awaiting checkout" : "None pending", noteColor: pending.length > 0 ? "text-yellow-700" : "text-ink-400", accent: "border-l-yellow-500" },
    { label: "Blanket Permits",  value: blanketCount || 0,    note: "On file", noteColor: "text-ink-400", accent: "border-l-purple-500" },
    { label: "Total Filed",      value: history.length,       note: "All time", noteColor: "text-ink-400", accent: "border-l-blue-500" },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
      {cards.map((card) => (
        <div
          key={card.label}
          className={`bg-white border border-ink/15 border-l-4 ${card.accent} px-6 py-5`}
        >
          <div className="text-[11px] font-semibold text-ink-500 uppercase tracking-[0.08em] mb-3">
            {card.label}
          </div>
          <div className="text-3xl font-bold text-steel-900 tabular-nums leading-none mb-2">
            {card.value}
          </div>
          <div className={`text-[11px] font-medium ${card.noteColor}`}>
            {card.note}
          </div>
        </div>
      ))}
    </div>
  );
}
