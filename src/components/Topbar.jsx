const VIEW_TITLES = {
  dashboard: "Dashboard",
  order: "Order Permits",
  history: "Permit History",
  blankets: "Blanket Permits",
  drivers: "Driver Database",
  settings: "Payment & Settings",
};

export default function Topbar({ activeView, onNewPermit }) {
  return (
    <div className="bg-navy-2 border-b border-subtle px-7 py-3.5 flex items-center gap-4 sticky top-0 z-40">
      <div className="text-base font-semibold">{VIEW_TITLES[activeView]}</div>
      <div className="ml-auto flex items-center gap-2.5">
        <button
          onClick={onNewPermit}
          className="bg-accent text-white border-none px-4 py-2 rounded-lg font-sans text-[13px] font-medium cursor-pointer transition-all hover:bg-accent-2 hover:-translate-y-px flex items-center gap-1.5"
        >
          + New Permit
        </button>
      </div>
    </div>
  );
}
