import { useState, useEffect } from "react";

const CC_STORAGE_KEY = "permitflow_payment_card";

const DEFAULT_CARD = {
  cardholderName: "Michael Caballero",
  cardNumber: "4242 4242 4242 4242",
  expMonth: "12",
  expYear: "2028",
  cvv: "123",
  billingStreet: "5979 NW 151ST ST STE 101",
  billingCity: "MIAMI LAKES",
  billingState: "FL",
  billingZip: "33014",
};

function loadCard() {
  try {
    const raw = localStorage.getItem(CC_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_CARD };
    return { ...DEFAULT_CARD, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_CARD };
  }
}

function detectBrand(num) {
  const n = (num || "").replace(/\s+/g, "");
  if (/^4/.test(n)) return "VISA";
  if (/^(5[1-5]|2[2-7])/.test(n)) return "MC";
  if (/^3[47]/.test(n)) return "AMEX";
  if (/^6(011|5)/.test(n)) return "DISC";
  return "CARD";
}

function formatCardNumber(val) {
  const digits = (val || "").replace(/\D/g, "").slice(0, 19);
  return digits.replace(/(.{4})/g, "$1 ").trim();
}

function maskCardNumber(num) {
  const digits = (num || "").replace(/\D/g, "");
  if (digits.length < 4) return "•••• •••• •••• ••••";
  const last4 = digits.slice(-4);
  return `•••• •••• •••• ${last4}`;
}

export default function SettingsView({ onToast }) {
  const [card, setCard] = useState(loadCard);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(card);

  const [email, setEmail] = useState("MICHAEL@MEGATRUCKINGLLC.COM");
  const [phone, setPhone] = useState("7869304305");

  useEffect(() => {
    setDraft(card);
  }, [card]);

  function startEdit() {
    setDraft(card);
    setEditing(true);
  }

  function cancelEdit() {
    setDraft(card);
    setEditing(false);
  }

  function saveCard() {
    const cleaned = {
      ...draft,
      cardNumber: (draft.cardNumber || "").replace(/\s+/g, ""),
      cvv: (draft.cvv || "").replace(/\D/g, ""),
      expMonth: (draft.expMonth || "").padStart(2, "0"),
      expYear: draft.expYear || "",
    };
    try {
      localStorage.setItem(CC_STORAGE_KEY, JSON.stringify(cleaned));
    } catch {}
    setCard(cleaned);
    setEditing(false);
    onToast?.("✓", "Payment card saved");
  }

  function updateDraft(patch) {
    setDraft((d) => ({ ...d, ...patch }));
  }

  const brand = detectBrand(card.cardNumber);
  const expDisplay =
    card.expMonth && card.expYear
      ? `${card.expMonth}/${String(card.expYear).slice(-2)}`
      : "••/••";

  return (
    <div className="max-w-[720px]">
      <div className="bg-navy-2 border border-subtle rounded-[14px] mb-5">
        <div className="px-[18px] py-3.5 border-b border-subtle flex items-center justify-between">
          <div className="text-[13.5px] font-semibold">Payment Card</div>
          <span className="text-[10px] text-txt-3 uppercase tracking-wide">
            Used by automation at checkout
          </span>
        </div>
        <div className="p-5">
          {/* Card preview */}
          <div className="mb-5">
            <div className="bg-gradient-to-br from-navy-3 to-navy-4 border border-subtle2 rounded-[12px] px-5 py-4 flex items-center gap-4">
              <span className="bg-accent rounded-[5px] text-[10px] font-bold text-white px-1.5 py-0.5 tracking-wide">
                {brand}
              </span>
              <div className="flex-1 min-w-0">
                <div className="font-mono text-[14px] text-txt-1 tracking-wider">
                  {maskCardNumber(card.cardNumber)}
                </div>
                <div className="text-[11px] text-txt-3 mt-0.5 truncate">
                  {card.cardholderName || "—"}
                </div>
              </div>
              <div className="text-right">
                <div className="text-[11px] text-txt-3">{expDisplay}</div>
                <div className="text-[10px] text-txt-3">
                  {card.billingCity || "—"}
                  {card.billingState ? `, ${card.billingState}` : ""} {card.billingZip}
                </div>
              </div>
            </div>
          </div>

          {!editing ? (
            <button
              onClick={startEdit}
              className="bg-transparent border border-subtle2 text-txt-2 rounded-md px-3.5 py-[7px] text-xs cursor-pointer hover:bg-navy-3 hover:text-txt-1 transition-all font-sans"
            >
              Edit Card Info
            </button>
          ) : (
            <div className="space-y-3.5">
              <div>
                <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                  Cardholder Name
                </label>
                <input
                  type="text"
                  value={draft.cardholderName}
                  onChange={(e) => updateDraft({ cardholderName: e.target.value })}
                  placeholder="Full name on card"
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                  Card Number
                </label>
                <input
                  type="text"
                  value={formatCardNumber(draft.cardNumber)}
                  onChange={(e) => updateDraft({ cardNumber: e.target.value })}
                  placeholder="0000 0000 0000 0000"
                  className="!font-mono"
                  inputMode="numeric"
                  autoComplete="off"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                    Exp Month
                  </label>
                  <input
                    type="text"
                    value={draft.expMonth}
                    onChange={(e) =>
                      updateDraft({ expMonth: e.target.value.replace(/\D/g, "").slice(0, 2) })
                    }
                    placeholder="MM"
                    inputMode="numeric"
                    maxLength={2}
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                    Exp Year
                  </label>
                  <input
                    type="text"
                    value={draft.expYear}
                    onChange={(e) =>
                      updateDraft({ expYear: e.target.value.replace(/\D/g, "").slice(0, 4) })
                    }
                    placeholder="YYYY"
                    inputMode="numeric"
                    maxLength={4}
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                    CVV
                  </label>
                  <input
                    type="text"
                    value={draft.cvv}
                    onChange={(e) =>
                      updateDraft({ cvv: e.target.value.replace(/\D/g, "").slice(0, 4) })
                    }
                    placeholder="123"
                    inputMode="numeric"
                    maxLength={4}
                    autoComplete="off"
                  />
                </div>
              </div>

              <hr className="border-t border-subtle" />

              <div className="text-[11px] uppercase tracking-wide text-txt-3 font-medium">
                Billing Address
              </div>

              <div>
                <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                  Street
                </label>
                <input
                  type="text"
                  value={draft.billingStreet}
                  onChange={(e) => updateDraft({ billingStreet: e.target.value })}
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                    City
                  </label>
                  <input
                    type="text"
                    value={draft.billingCity}
                    onChange={(e) => updateDraft({ billingCity: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                    State
                  </label>
                  <input
                    type="text"
                    value={draft.billingState}
                    onChange={(e) =>
                      updateDraft({ billingState: e.target.value.toUpperCase().slice(0, 2) })
                    }
                    maxLength={2}
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                    Zip
                  </label>
                  <input
                    type="text"
                    value={draft.billingZip}
                    onChange={(e) =>
                      updateDraft({ billingZip: e.target.value.replace(/\D/g, "").slice(0, 10) })
                    }
                    inputMode="numeric"
                  />
                </div>
              </div>

              <div className="flex gap-2 pt-1">
                <button
                  onClick={saveCard}
                  className="bg-accent text-white border-none px-3.5 py-[7px] rounded-lg text-xs font-medium cursor-pointer hover:bg-accent-2 transition-all font-sans"
                >
                  Save Card
                </button>
                <button
                  onClick={cancelEdit}
                  className="bg-transparent border border-subtle2 text-txt-2 rounded-md px-3.5 py-[7px] text-xs cursor-pointer hover:bg-navy-3 hover:text-txt-1 transition-all font-sans"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="bg-navy-2 border border-subtle rounded-[14px]">
        <div className="px-[18px] py-3.5 border-b border-subtle">
          <div className="text-[13.5px] font-semibold">Receipt Delivery</div>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-2 gap-3.5 mb-3">
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                Email
              </label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                Phone (RingCentral)
              </label>
              <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
            </div>
          </div>
          <button
            onClick={() => onToast?.("✓", "Settings saved")}
            className="bg-accent text-white border-none px-3.5 py-[7px] rounded-lg text-xs font-medium cursor-pointer hover:bg-accent-2 transition-all font-sans"
          >
            Save Settings
          </button>

          <hr className="border-t border-subtle my-[18px]" />

          <div className="text-[11px] uppercase tracking-wide text-txt-3 font-medium mb-3">
            Georgia Portal Account
          </div>
          <div className="grid grid-cols-2 gap-3.5">
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                Account No.
              </label>
              <input type="text" value="82761" readOnly className="!opacity-60 !cursor-not-allowed" />
            </div>
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">
                Billing Address
              </label>
              <input
                type="text"
                value="5979 NW 151ST ST STE 101"
                readOnly
                className="!opacity-60 !cursor-not-allowed"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
