const VIEW_TITLES = {
  dashboard: "Dashboard",
  order:     "Order Permits",
  history:   "Permit History",
  blankets:  "Blanket Permits",
  drivers:   "Driver Database",
  settings:  "Payment & Settings",
};

export default function Topbar({ activeView, onNewPermit }) {
  const title = VIEW_TITLES[activeView] || VIEW_TITLES.dashboard;
  return (
    <div className="bg-bone border-b border-ink/15 px-8 lg:px-12 h-[80px] flex items-center gap-6 sticky top-0 z-40">
      <h1 className="font-serif font-black text-2xl tracking-tight text-steel-900 leading-none">
        {title}
      </h1>
      <div className="ml-auto flex items-center gap-3">
        <button
          onClick={onNewPermit}
          className="bg-amber text-white border-none px-6 py-3 rounded-sm font-sans text-[11px] font-semibold uppercase tracking-[0.06em] cursor-pointer transition-colors hover:bg-amber-600"
        >
          + New Permit
        </button>
      </div>
    </div>
  );
}
