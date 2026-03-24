import { useState, useCallback } from "react";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import Toast from "./components/Toast";
import DashboardView from "./components/DashboardView";
import OrderForm from "./components/OrderForm";
import HistoryTable from "./components/HistoryTable";
import BlanketPermits from "./components/BlanketPermits";
import DriversView from "./components/DriversView";
import SettingsView from "./components/SettingsView";

export default function App() {
  const [activeView, setActiveView] = useState("dashboard");
  const [toast, setToast] = useState({ visible: false, icon: "", message: "" });

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
        return <HistoryTable />;
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

  return (
    <div className="flex min-h-screen">
      <Sidebar activeView={activeView} onNavigate={setActiveView} />
      <main className="ml-[220px] flex-1">
        <Topbar activeView={activeView} onNewPermit={() => setActiveView("order")} />
        <div className="p-7">
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
