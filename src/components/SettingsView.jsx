import { useState, useEffect } from "react";
import { fetchPaymentCard, updatePaymentCard } from "../api";

function formatCardNumber(val) {
  const digits = (val || "").replace(/\D/g, "").slice(0, 19);
  return digits.replace(/(.{4})/g, "$1 ").trim();
}

const EMPTY_DRAFT = {
  cardholderName: "",
  cardNumber: "",
  expMonth: "",
  expYear: "",
  cvv: "",
  billingStreet: "",
  billingCity: "",
  billingState: "",
  billingZip: "",
};

export default function SettingsView({ onToast }) {
  const [card, setCard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(EMPTY_DRAFT);

  const [email, setEmail] = useState("MICHAEL@MEGATRUCKINGLLC.COM");
  const [phone, setPhone] = useState("7869304305");

  useEffect(() => {
    // Remove legacy localStorage card data
    try { localStorage.removeItem("permitflow_payment_card"); } catch {}

    fetchPaymentCard()
      .then((data) => {
        setCard(data?.hasCard ? data : null);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  function startEdit() {
    setDraft({
      cardholderName: card?.cardholderName || "",
      cardNumber: "",
      expMonth: card?.expMonth || "",
      expYear: card?.expYear || "",
      cvv: "",
      billingStreet: card?.billingStreet || "",
      billingCity: card?.billingCity || "",
      billingState: card?.billingState || "",
      billingZip: card?.billingZip || "",
    });
    setEditing(true);
  }

  function cancelEdit() {
    setEditing(false);
  }

  async function saveCard() {
    const cleaned = {
      ...draft,
      cardNumber: (draft.cardNumber || "").replace(/\s+/g, ""),
      cvv: (draft.cvv || "").replace(/\D/g, ""),
      expMonth: (draft.expMonth || "").padStart(2, "0"),
      expYear: draft.expYear || "",
    };
    if (!cleaned.cardNumber || !cleaned.cvv) {
      onToast?.("!", "Card number and CVV are required");
      return;
    }
    setSaving(true);
    try {
      await updatePaymentCard(cleaned);
      const updated = await fetchPaymentCard();
      setCard(updated?.hasCard ? updated : null);
      setEditing(false);
      onToast?.("✓", "Payment card saved securely");
    } catch {
      onToast?.("✕", "Failed to save card");
    } finally {
      setSaving(false);
    }
  }

  function updateDraft(patch) {
    setDraft((d) => ({ ...d, ...patch }));
  }

  const brand = card?.brand || "CARD";
  const expDisplay =
    card?.expMonth && card?.expYear
      ? `${card.expMonth}/${String(card.expYear).slice(-2)}`
      : "••/••";

  return (
    <div className="max-w-[720px]">
      <div className="bg-white border border-ink/15 mb-5">
        <div className="px-[18px] py-3.5 border-b border-ink/15 flex items-center justify-between">
          <div className="text-[13.5px] font-semibold">Payment Card</div>
          <span className="text-[10px] text-ink-400 uppercase tracking-wide">
            Encrypted server-side
          </span>
        </div>
        <div className="p-5">
          {loading ? (
            <div className="text-[12px] text-ink-400 py-4 text-center">Loading...</div>
          ) : (
            <>
              {/* Card preview */}
              <div className="mb-6">
                {card ? (
                  <div className="relative bg-white border border-ink/15 rounded-sm px-6 py-5 overflow-hidden shadow-card">
                    {/* Amber accent stripe */}
                    <div className="absolute top-0 left-0 h-full w-1 bg-amber" />
                    <div className="flex items-start justify-between mb-8">
                      <div>
                        <div className="text-[9px] uppercase tracking-[0.22em] font-semibold text-amber-600 mb-1">
                          On File
                        </div>
                        <div className="text-[11px] text-ink-500 font-medium">
                          Payment Card
                        </div>
                      </div>
                      <span className="bg-amber rounded-sm text-[10px] font-bold text-white px-2 py-1 tracking-wide uppercase">
                        {brand}
                      </span>
                    </div>
                    <div className="font-mono text-[20px] tracking-[0.15em] text-steel-900 font-semibold mb-5">
                      •••• •••• •••• <span className="text-amber-600">{card.lastFour}</span>
                    </div>
                    <div className="flex items-end justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="text-[9px] uppercase tracking-[0.15em] text-ink-400 font-semibold mb-1">
                          Cardholder
                        </div>
                        <div className="text-[13px] text-steel-900 font-semibold truncate">
                          {card.cardholderName || "—"}
                        </div>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <div className="text-[9px] uppercase tracking-[0.15em] text-ink-400 font-semibold mb-1">
                          Expires
                        </div>
                        <div className="text-[13px] text-steel-900 font-semibold tabular-nums">
                          {expDisplay}
                        </div>
                      </div>
                    </div>
                    {(card.billingCity || card.billingState || card.billingZip) && (
                      <div className="mt-4 pt-4 border-t border-ink/10 text-[11px] text-ink-500">
                        {card.billingCity || "—"}
                        {card.billingState ? `, ${card.billingState}` : ""} {card.billingZip}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="bg-white border-2 border-dashed border-ink/20 rounded-sm px-6 py-10 text-center">
                    <div className="text-[13px] text-ink-500 font-medium mb-1">No card on file</div>
                    <div className="text-[11px] text-ink-400">Add a card to enable automated payments.</div>
                  </div>
                )}
              </div>

              {!editing ? (
                <button
                  onClick={startEdit}
                  className="bg-transparent border border-ink/20 text-ink-500 rounded-sm px-3.5 py-[7px] text-xs cursor-pointer hover:bg-bone-3 hover:text-steel-900 transition-all font-sans"
                >
                  {card ? "Update Card Info" : "Add Card"}
                </button>
              ) : (
                <div className="space-y-3.5">
                  <div className="text-[10px] text-amber-600 mb-1">
                    Card number and CVV must be re-entered each time for security.
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
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
                    <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
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
                      <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
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
                      <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
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
                      <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
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

                  <hr className="border-t border-ink/15" />

                  <div className="text-[11px] uppercase tracking-wide text-ink-400 font-medium">
                    Billing Address
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
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
                      <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
                        City
                      </label>
                      <input
                        type="text"
                        value={draft.billingCity}
                        onChange={(e) => updateDraft({ billingCity: e.target.value })}
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
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
                      <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
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
                      disabled={saving}
                      className="bg-amber text-white border-none px-3.5 py-[7px] rounded-sm text-xs font-medium cursor-pointer hover:bg-amber-600 transition-all font-sans disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {saving ? "Saving..." : "Save Card"}
                    </button>
                    <button
                      onClick={cancelEdit}
                      disabled={saving}
                      className="bg-transparent border border-ink/20 text-ink-500 rounded-sm px-3.5 py-[7px] text-xs cursor-pointer hover:bg-bone-3 hover:text-steel-900 transition-all font-sans"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <div className="bg-white border border-ink/15">
        <div className="px-[18px] py-3.5 border-b border-ink/15">
          <div className="text-[13.5px] font-semibold">Receipt Delivery</div>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-2 gap-3.5 mb-3">
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
                Email
              </label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
                Phone (RingCentral)
              </label>
              <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
            </div>
          </div>
          <button
            onClick={() => onToast?.("✓", "Settings saved")}
            className="bg-amber text-white border-none px-3.5 py-[7px] rounded-sm text-xs font-medium cursor-pointer hover:bg-amber-600 transition-all font-sans"
          >
            Save Settings
          </button>

          <hr className="border-t border-ink/15 my-[18px]" />

          <div className="text-[11px] uppercase tracking-wide text-ink-400 font-medium mb-3">
            Georgia Portal Account
          </div>
          <div className="grid grid-cols-2 gap-3.5">
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
                Account No.
              </label>
              <input type="text" value="82761" readOnly className="!opacity-60 !cursor-not-allowed" />
            </div>
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
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
