import { useState } from "react";

export default function SettingsView({ onToast }) {
  const [ccInfo, setCcInfo] = useState({
    name: "Michael Caballero",
    last4: "4500",
    exp: "••/••",
    city: "MIAMI LAKES",
    zip: "33014",
  });

  const [email, setEmail] = useState("MICHAEL@MEGATRUCKINGLLC.COM");
  const [phone, setPhone] = useState("7869304305");

  return (
    <div className="max-w-[560px]">
      <div className="bg-navy-2 border border-subtle rounded-[14px]">
        <div className="px-[18px] py-3.5 border-b border-subtle">
          <div className="text-[13.5px] font-semibold">Payment Methods</div>
        </div>
        <div className="p-5">
          {/* Active Card */}
          <div className="mb-5">
            <div className="text-[11px] uppercase tracking-wide text-txt-3 font-medium mb-3">
              Active Ramp Card
            </div>
            <div className="bg-navy-3 border border-subtle2 rounded-[10px] px-4 py-3.5 flex items-center gap-3 mb-2.5">
              <span className="bg-accent rounded-[5px] text-[10px] font-bold text-white px-1.5 py-0.5 tracking-wide">
                VISA
              </span>
              <div className="flex-1">
                <div className="font-mono text-[13px]">•••• •••• •••• {ccInfo.last4}</div>
                <div className="text-[11px] text-txt-3 mt-0.5">{ccInfo.name}</div>
              </div>
              <div className="text-right">
                <div className="text-[11px] text-txt-3">{ccInfo.exp}</div>
                <div className="text-[10px] text-txt-3">{ccInfo.city}, {ccInfo.zip}</div>
              </div>
            </div>
            <button
              onClick={() => onToast?.("ℹ", "Card update modal coming soon")}
              className="bg-transparent border border-subtle2 text-txt-2 rounded-md px-3.5 py-[7px] text-xs cursor-pointer hover:bg-navy-3 hover:text-txt-1 transition-all font-sans"
            >
              Update Card Info
            </button>
          </div>

          <hr className="border-t border-subtle my-[18px]" />

          {/* Receipt Delivery */}
          <div className="mb-5">
            <div className="text-[11px] uppercase tracking-wide text-txt-3 font-medium mb-3">
              Receipt Delivery
            </div>
            <div className="grid grid-cols-2 gap-3.5 mb-3">
              <div>
                <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">Email</label>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div>
                <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">Phone (RingCentral)</label>
                <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
              </div>
            </div>
            <button
              onClick={() => onToast?.("✓", "Settings saved")}
              className="bg-accent text-white border-none px-3.5 py-[7px] rounded-lg text-xs font-medium cursor-pointer hover:bg-accent-2 transition-all font-sans"
            >
              Save Settings
            </button>
          </div>

          <hr className="border-t border-subtle my-[18px]" />

          {/* Portal Account */}
          <div>
            <div className="text-[11px] uppercase tracking-wide text-txt-3 font-medium mb-3">
              Georgia Portal Account
            </div>
            <div className="grid grid-cols-2 gap-3.5">
              <div>
                <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">Account No.</label>
                <input type="text" value="82761" readOnly className="!opacity-60 !cursor-not-allowed" />
              </div>
              <div>
                <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">Billing Address</label>
                <input type="text" value="5979 NW 151ST ST STE 101" readOnly className="!opacity-60 !cursor-not-allowed" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
