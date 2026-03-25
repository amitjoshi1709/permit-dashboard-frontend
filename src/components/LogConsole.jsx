const STATUS_COLORS = {
  success: "text-[#3EDB7A]",
  error: "text-permit-red2",
  info: "text-accent-2",
};

export default function LogConsole({ messages }) {
  if (!messages || messages.length === 0) return null;

  return (
    <div className="bg-navy/80 border border-subtle rounded-lg p-3.5 max-h-64 overflow-y-auto font-mono text-[12px]">
      {messages.map((msg, i) => (
        <div key={i} className="text-txt-2 leading-relaxed">
          <span className="text-accent-2">[{msg.timestamp}]</span>{" "}
          {msg.status && (
            <span className={STATUS_COLORS[msg.status] || "text-txt-2"}>
              {msg.status === "success" ? "✓" : msg.status === "error" ? "✗" : "→"}
            </span>
          )}{" "}
          {msg.text}
        </div>
      ))}
    </div>
  );
}
