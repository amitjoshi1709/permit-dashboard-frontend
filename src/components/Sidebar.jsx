import { logout } from "../api";
import logo from "../assets/logo.png";

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard",       section: "Main" },
  { key: "order",     label: "Order Permits",   section: "Main",    badge: "+" },
  { key: "history",   label: "Permit History",  section: "Records" },
  { key: "blankets",  label: "Blanket Permits", section: "Records" },
  { key: "drivers",   label: "Driver Database", section: "Manage" },
  { key: "settings",  label: "Payment & CC",    section: "Settings" },
];

export default function Sidebar({ activeView, onNavigate }) {
  let lastSection = "";

  return (
    <aside className="w-[240px] min-h-screen bg-steel-900 text-bone fixed top-0 left-0 bottom-0 z-50 flex flex-col border-r border-black/20">
      {/* Logo */}
      <div className="px-6 pt-6 pb-5 border-b border-white/10">
        <div className="flex items-center gap-3">
          <img src={logo} alt="PermitFlo" className="w-24 h-24 object-contain rounded-sm bg-white/10 p-1.5" />
          <div>
            <div className="font-serif font-black text-[17px] leading-none text-bone">PermitFlo</div>
            <div className="text-[9px] text-amber-400 font-semibold uppercase tracking-[0.22em] mt-1.5">
              Est. 2025
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4">
        {NAV_ITEMS.map((item) => {
          const showSection = item.section !== lastSection;
          lastSection = item.section;
          const isActive = activeView === item.key;
          return (
            <div key={item.key}>
              {showSection && (
                <div className="text-[9px] text-white/50 tracking-[0.22em] uppercase px-6 pt-5 pb-2 font-semibold">
                  {item.section}
                </div>
              )}
              <button
                onClick={() => onNavigate(item.key)}
                className={`w-full flex items-center gap-3 px-6 py-2.5 text-[13px] cursor-pointer transition-colors border-none text-left ${
                  isActive
                    ? "bg-white/5 text-amber-400 font-semibold"
                    : "bg-transparent text-white/80 hover:bg-white/[0.03] hover:text-bone font-medium"
                }`}
              >
                <span
                  className={`block h-4 w-px transition-colors ${
                    isActive ? "bg-amber-400" : "bg-transparent"
                  }`}
                />
                <span className="uppercase tracking-[0.08em] text-[11px]">{item.label}</span>
                {item.badge && (
                  <span className="ml-auto bg-amber text-white text-[10px] font-semibold rounded-sm px-1.5 py-0.5 min-w-[18px] text-center leading-none">
                    {item.badge}
                  </span>
                )}
              </button>
            </div>
          );
        })}
      </nav>

      {/* User */}
      <div className="px-6 py-5 border-t border-white/10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-sm bg-amber/20 border border-amber/40 flex items-center justify-center text-[11px] font-semibold text-amber-400 flex-shrink-0">
            MC
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[12px] font-semibold text-bone truncate">Michael Caballero</div>
            <div className="text-[10px] text-white/60 uppercase tracking-wider">Dispatcher</div>
          </div>
          <button
            onClick={logout}
            title="Sign out"
            className="text-[10px] text-white/60 hover:text-amber-400 cursor-pointer bg-transparent border-none transition-colors uppercase tracking-[0.08em] font-semibold"
          >
            Sign out
          </button>
        </div>
      </div>
    </aside>
  );
}
