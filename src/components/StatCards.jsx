function parseDate(str) {
  if (!str) return null;
  // Handle both MM/DD/YYYY and YYYY-MM-DD
  if (str.includes("/")) {
    const [m, d, y] = str.split("/");
    return new Date(parseInt(y), parseInt(m) - 1, parseInt(d));
  }
  return new Date(str);
}

export default function StatCards({ history, blanketCount }) {
  const active = history.filter((p) => p.status === "Active");
  const pending = history.filter((p) => p.status === "Pending");
  const pendingFees = pending.reduce((s, p) => s + (p.fee || 0), 0);

  const now = new Date();
  const thisMonth = history.filter((p) => {
    const d = parseDate(p.effDate);
    return d && d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
  });

  const expiringSoon = active.filter((p) => {
    const expDate = parseDate(p.expDate);
    if (!expDate || isNaN(expDate)) return false;
    const diff = Math.round((expDate - now) / 86400000);
    return diff <= 7 && diff >= 0;
  });

  const cards = [
    { label: "Active Permits", value: active.length, sub: `${expiringSoon.length} expiring this week`, color: "bg-accent" },
    { label: "Pending Payment", value: pending.length, sub: `$${pendingFees} total`, color: "bg-gold" },
    { label: "Issued This Month", value: thisMonth.length, sub: "GA Trip + Fuel", color: "bg-permit-green" },
    { label: "Blanket Permits", value: blanketCount || 0, sub: "On file", color: "bg-permit-red" },
  ];

  return (
    <div className="grid grid-cols-4 gap-3.5 mb-6">
      {cards.map((card) => (
        <div
          key={card.label}
          className="bg-navy-2 border border-subtle rounded-[14px] px-[18px] py-4 relative overflow-hidden"
        >
          <div className={`absolute top-0 left-0 right-0 h-0.5 ${card.color}`} />
          <div className="text-[11px] text-txt-3 uppercase tracking-wide font-medium mb-1.5">
            {card.label}
          </div>
          <div className="text-[26px] font-semibold leading-none">{card.value}</div>
          <div className="text-[11px] text-txt-3 mt-1">{card.sub}</div>
        </div>
      ))}
    </div>
  );
}
