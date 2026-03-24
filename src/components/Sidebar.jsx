const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", section: "Main" },
  { key: "order", label: "Order Permits", section: "Main", badge: "+" },
  { key: "history", label: "Permit History", section: "Records" },
  { key: "blankets", label: "Blanket Permits", section: "Records" },
  { key: "drivers", label: "Driver Database", section: "Manage" },
  { key: "settings", label: "Payment & CC", section: "Settings" },
];

export default function Sidebar({ activeView, onNavigate }) {
  let lastSection = "";

  return (
    <aside className="w-[220px] min-h-screen bg-navy-2 border-r border-subtle fixed top-0 left-0 bottom-0 z-50 flex flex-col">
      {/* Logo */}
      <div className="px-[18px] py-5 border-b border-subtle">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-accent rounded-lg flex items-center justify-center text-base">
            🚛
          </div>
          <div>
            <div className="font-semibold text-[15px] leading-tight text-txt-1">Mega Trucking</div>
            <div className="text-[10px] text-txt-3 font-normal tracking-wider uppercase mt-px">Permit Hub</div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-2.5">
        {NAV_ITEMS.map((item) => {
          const showSection = item.section !== lastSection;
          lastSection = item.section;
          return (
            <div key={item.key}>
              {showSection && (
                <div className="text-[10px] text-txt-3 tracking-widest uppercase px-[18px] pt-2.5 pb-1 font-medium">
                  {item.section}
                </div>
              )}
              <button
                onClick={() => onNavigate(item.key)}
                className={`w-full flex items-center gap-2.5 px-[18px] py-[9px] text-[13.5px] cursor-pointer transition-all border-none bg-transparent ${
                  activeView === item.key
                    ? "bg-navy-3 text-accent-2 font-medium"
                    : "text-txt-2 hover:bg-navy-3 hover:text-txt-1"
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                    activeView === item.key ? "bg-accent-2" : "bg-txt-3"
                  }`}
                />
                {item.label}
                {item.badge && (
                  <span className="ml-auto bg-accent text-white text-[10px] font-semibold rounded-[10px] px-1.5 min-w-[18px] text-center">
                    {item.badge}
                  </span>
                )}
              </button>
            </div>
          );
        })}
      </nav>

      {/* User */}
      <div className="px-[18px] py-3.5 border-t border-subtle">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-steel flex items-center justify-center text-[11px] font-semibold flex-shrink-0">
            MC
          </div>
          <div>
            <div className="text-xs font-medium">Michael Caballero</div>
            <div className="text-[10px] text-txt-3">Dispatcher</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
