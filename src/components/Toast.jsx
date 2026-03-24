import { useEffect } from "react";

export default function Toast({ icon, message, visible, onClose }) {
  useEffect(() => {
    if (visible) {
      const timer = setTimeout(onClose, 3000);
      return () => clearTimeout(timer);
    }
  }, [visible, onClose]);

  return (
    <div
      className={`fixed bottom-6 right-6 bg-navy-2 border border-subtle2 rounded-[10px] px-[18px] py-3 text-[13px] text-txt-1 shadow-[0_8px_32px_rgba(0,0,0,0.4)] z-[2000] flex items-center gap-2.5 max-w-[320px] transition-all duration-200 ${
        visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-5 pointer-events-none"
      }`}
    >
      <span className="text-base">{icon}</span>
      <span>{message}</span>
    </div>
  );
}
