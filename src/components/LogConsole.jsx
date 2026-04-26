const STATUS_COLORS = {
  success: "text-[#2E6A3B]",
  error: "text-[#7A2C22]",
  info: "text-amber-600",
};

export default function LogConsole({ messages }) {
  if (!messages || messages.length === 0) return null;

  return (
    <div className="bg-white border border-ink/15 rounded-sm p-3.5 max-h-64 overflow-y-auto font-mono text-[12px]">
      {messages.map((msg, i) => (
        <div key={i} className="text-ink-500 leading-relaxed">
          <span className="text-amber-600">[{msg.timestamp}]</span>{" "}
          {msg.status && (
            <span className={STATUS_COLORS[msg.status] || "text-ink-500"}>
              {msg.status === "success" ? "✓" : msg.status === "error" ? "✗" : "→"}
            </span>
          )}{" "}
          {msg.text}
        </div>
      ))}
    </div>
  );
}
