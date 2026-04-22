import { useState, useCallback, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import Toast from "./components/Toast";
import Login from "./components/Login";
import DashboardView from "./components/DashboardView";
import OrderForm from "./components/OrderForm";
import HistoryTable from "./components/HistoryTable";
import BlanketPermits from "./components/BlanketPermits";
import DriversView from "./components/DriversView";
import SettingsView from "./components/SettingsView";
import { verifyToken } from "./api";

export default function App() {
  const [authState, setAuthState] = useState("checking"); // "checking" | "authed" | "unauthed"
  const [activeView, setActiveView] = useState("dashboard");
  const [toast, setToast] = useState({ visible: false, icon: "", message: "" });

  useEffect(() => {
    verifyToken().then((ok) => setAuthState(ok ? "authed" : "unauthed"));
  }, []);

  const showToast = useCallback((icon, message) => {
    setToast({ visible: true, icon, message });
  }, []);

  const hideToast = useCallback(() => {
    setToast((prev) => ({ ...prev, visible: false }));
  }, []);

  function renderView() {
    switch (activeView) {
      case "dashboard":
        return <DashboardView onNavigate={setActiveView} />;
      case "order":
        return <OrderForm onToast={showToast} />;
      case "history":
        return <HistoryTable onNavigate={setActiveView} onToast={showToast} />;
      case "blankets":
        return <BlanketPermits onToast={showToast} />;
      case "drivers":
        return <DriversView onToast={showToast} />;
      case "settings":
        return <SettingsView onToast={showToast} />;
      default:
        return <DashboardView onNavigate={setActiveView} />;
    }
  }

  if (authState === "checking") {
    return <div className="min-h-screen flex items-center justify-center bg-bone text-ink-400 text-[13px]">Loading…</div>;
  }

  if (authState === "unauthed") {
    return <Login onLogin={() => setAuthState("authed")} />;
  }

  return (
    <div className="flex min-h-screen bg-bone text-ink">
      <Sidebar activeView={activeView} onNavigate={setActiveView} />
      <main className="ml-[240px] flex-1 flex flex-col min-h-screen">
        <Topbar activeView={activeView} onNewPermit={() => setActiveView("order")} />
        <div className="flex-1 px-8 lg:px-12 py-10 max-w-[1400px] w-full">
          {renderView()}
        </div>
      </main>
      <Toast
        icon={toast.icon}
        message={toast.message}
        visible={toast.visible}
        onClose={hideToast}
      />
    </div>
  );
}
