import { useState, useEffect } from "react";
import { fetchDrivers, createDriver, updateDriver, deleteDriver, fetchMegaInsurance, updateMegaInsurance, DRIVER_TYPES, COMPANY_TYPES, COMPANY_DEFAULTS } from "../api";

const EMPTY_FORM = {
  firstName: "", lastName: "", tractor: "", driverType: "",
  year: "", make: "", vin: "", tagNumber: "", tagState: "",
  usdot: "", fein: "",
  insuranceCompany: "", insuranceEffective: "", insuranceExpiration: "", policyNumber: "",
};

function isCompanyType(type) {
  return COMPANY_TYPES.includes(type);
}

function applyTypeDefaults(form, type) {
  if (isCompanyType(type)) {
    return {
      ...form, driverType: type,
      usdot: COMPANY_DEFAULTS.usdot, fein: "",
      insuranceCompany: COMPANY_DEFAULTS.insuranceCompany,
      insuranceEffective: COMPANY_DEFAULTS.insuranceEffective,
      insuranceExpiration: COMPANY_DEFAULTS.insuranceExpiration,
      policyNumber: COMPANY_DEFAULTS.policyNumber,
    };
  }
  return {
    ...form, driverType: type,
    usdot: "", fein: "", insuranceCompany: "",
    insuranceEffective: "", insuranceExpiration: "", policyNumber: "",
  };
}

function DriverForm({ form, setForm, onSave, onCancel, saving, title }) {
  const isCompany = isCompanyType(form.driverType);

  function handleTypeChange(type) {
    setForm((f) => applyTypeDefaults(f, type));
  }

  function updateField(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  const canSave = form.firstName.trim() && form.lastName.trim() && form.tractor.trim() &&
    form.driverType && form.year.trim() && form.make.trim() && form.vin.trim() &&
    form.tagNumber.trim() && form.tagState.trim() && form.usdot.trim() &&
    form.insuranceCompany.trim() && form.insuranceEffective.trim() &&
    form.insuranceExpiration.trim() && form.policyNumber.trim() &&
    (isCompany || form.fein.trim());

  return (
    <div className="px-[18px] py-5 border-b border-subtle bg-navy-3/30">
      <div className="text-[11px] uppercase tracking-wide text-txt-3 font-medium mb-4">{title}</div>

      {/* Row 1: Name */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <Field label="First Name" value={form.firstName} onChange={(v) => updateField("firstName", v)} placeholder="e.g. John" />
        <Field label="Last Name" value={form.lastName} onChange={(v) => updateField("lastName", v)} placeholder="e.g. Smith" />
      </div>

      {/* Row 2: Driver Type + Tractor */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div>
          <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">Driver Type</label>
          <select value={form.driverType} onChange={(e) => handleTypeChange(e.target.value)}>
            <option value="">— Select —</option>
            {DRIVER_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <Field label="Tractor #" value={form.tractor} onChange={(v) => updateField("tractor", v)} placeholder="e.g. F894" />
        <Field label="Year" value={form.year} onChange={(v) => updateField("year", v)} placeholder="e.g. 2016" />
      </div>

      {/* Row 3: Vehicle details */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        <Field label="Make" value={form.make} onChange={(v) => updateField("make", v)} placeholder="e.g. Freightliner" />
        <Field label="VIN" value={form.vin} onChange={(v) => updateField("vin", v)} placeholder="Full VIN" />
        <div className="grid grid-cols-2 gap-2">
          <Field label="Tag #" value={form.tagNumber} onChange={(v) => updateField("tagNumber", v)} placeholder="e.g. FL-1234" />
          <Field label="Tag State" value={form.tagState} onChange={(v) => updateField("tagState", v)} placeholder="e.g. FL" />
        </div>
      </div>

      {/* Divider */}
      <hr className="border-t border-subtle my-4" />

      {/* Company info notice */}
      {form.driverType && isCompany && (
        <div className="rounded-lg px-3.5 py-2.5 text-[12.5px] leading-relaxed bg-accent/10 border border-accent/20 text-accent-2 flex items-start gap-2 mb-3">
          <span className="text-sm flex-shrink-0 mt-px">i</span>
          <span>Company driver ({form.driverType}) — USDOT and insurance auto-filled with Mega Trucking defaults. No FEIN required.</span>
        </div>
      )}

      {form.driverType && !isCompany && (
        <div className="rounded-lg px-3.5 py-2.5 text-[12.5px] leading-relaxed bg-permit-orange/10 border border-permit-orange/25 text-[#FFD166] flex items-start gap-2 mb-3">
          <span className="text-sm flex-shrink-0 mt-px">⚠</span>
          <span>Independent driver ({form.driverType}) — enter their own USDOT, FEIN, and insurance information below.</span>
        </div>
      )}

      {/* Row 4: USDOT + FEIN */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        <Field
          label="USDOT"
          value={form.usdot}
          onChange={(v) => updateField("usdot", v)}
          placeholder="e.g. 2582238"
          readOnly={isCompany}
        />
        {!isCompany && (
          <Field
            label="FEIN"
            value={form.fein}
            onChange={(v) => updateField("fein", v)}
            placeholder="e.g. 84-7291003"
          />
        )}
      </div>

      {/* Row 5: Insurance */}
      <div className="text-[11px] uppercase tracking-wide text-txt-3 font-medium mb-2 mt-1">Insurance</div>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <Field
          label="Company Name"
          value={form.insuranceCompany}
          onChange={(v) => updateField("insuranceCompany", v)}
          placeholder="e.g. Prime Property and Casualty"
          readOnly={isCompany}
        />
        <Field
          label="Policy Number"
          value={form.policyNumber}
          onChange={(v) => updateField("policyNumber", v)}
          placeholder="e.g. PC24040671"
          readOnly={isCompany}
        />
      </div>
      <div className="grid grid-cols-2 gap-3 mb-4">
        <Field
          label="Effective Date"
          value={form.insuranceEffective}
          onChange={(v) => updateField("insuranceEffective", v)}
          placeholder="MM/DD/YYYY"
          readOnly={isCompany}
        />
        <Field
          label="Expiration Date"
          value={form.insuranceExpiration}
          onChange={(v) => updateField("insuranceExpiration", v)}
          placeholder="MM/DD/YYYY"
          readOnly={isCompany}
        />
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <button
          onClick={onSave}
          disabled={saving || !canSave}
          className="bg-accent text-white border-none px-5 py-[9px] rounded-lg text-[13px] font-medium cursor-pointer hover:bg-accent-2 transition-all font-sans disabled:bg-navy-3 disabled:text-txt-3 disabled:cursor-not-allowed"
        >
          {saving ? "Saving..." : "Save Driver"}
        </button>
        <button
          onClick={onCancel}
          className="bg-transparent border border-subtle2 text-txt-2 px-5 py-[9px] rounded-lg text-[13px] cursor-pointer hover:bg-navy-3 hover:text-txt-1 transition-all font-sans"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, readOnly }) {
  return (
    <div>
      <label className="block text-[11px] font-medium uppercase tracking-wide text-txt-3 mb-1.5">{label}</label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        readOnly={readOnly}
        className={readOnly ? "!opacity-60 !cursor-not-allowed" : ""}
      />
    </div>
  );
}

export default function DriversView({ onToast }) {
  const [drivers, setDrivers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({ ...EMPTY_FORM });
  const [showAdd, setShowAdd] = useState(false);
  const [addForm, setAddForm] = useState({ ...EMPTY_FORM });
  const [saving, setSaving] = useState(false);
  const [driverSearch, setDriverSearch] = useState("");

  // Mega insurance (shared across all F/LP/T drivers)
  const [megaInsurance, setMegaInsurance] = useState({
    insuranceCompany: "", insuranceEffective: "",
    insuranceExpiration: "", policyNumber: "",
  });
  const [editingMega, setEditingMega] = useState(false);
  const [megaForm, setMegaForm] = useState({
    insuranceCompany: "", insuranceEffective: "",
    insuranceExpiration: "", policyNumber: "",
  });
  const [savingMega, setSavingMega] = useState(false);

  function load() {
    setLoading(true);
    fetchDrivers()
      .then((data) => {
        setDrivers(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(() => {
        setDrivers([]);
        setLoading(false);
        onToast?.("⚠", "Failed to load drivers");
      });
  }

  function loadMegaInsurance() {
    fetchMegaInsurance()
      .then((data) => setMegaInsurance(data || {}))
      .catch(() => {});
  }

  useEffect(() => { load(); loadMegaInsurance(); }, []);

  function startEditMega() {
    setMegaForm({ ...megaInsurance });
    setEditingMega(true);
  }

  function cancelEditMega() {
    setEditingMega(false);
  }

  async function saveMegaInsurance() {
    setSavingMega(true);
    try {
      const result = await updateMegaInsurance(megaForm);
      onToast?.("✓", `Mega insurance updated · ${result.updated || 0} driver(s)`);
      setEditingMega(false);
      loadMegaInsurance();
      load();
    } catch {
      onToast?.("⚠", "Failed to update Mega insurance");
    } finally {
      setSavingMega(false);
    }
  }

  function startEdit(driver) {
    setEditingId(driver.id);
    setExpandedId(null);
    setShowAdd(false);
    setEditForm({
      firstName: driver.firstName || "", lastName: driver.lastName || "",
      tractor: driver.tractor || "", driverType: driver.driverType || "",
      year: driver.year || "", make: driver.make || "",
      vin: driver.vin || "", tagNumber: driver.tagNumber || "", tagState: driver.tagState || "",
      usdot: driver.usdot || "", fein: driver.fein || "",
      insuranceCompany: driver.insuranceCompany || "",
      insuranceEffective: driver.insuranceEffective || "",
      insuranceExpiration: driver.insuranceExpiration || "",
      policyNumber: driver.policyNumber || "",
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setEditForm({ ...EMPTY_FORM });
  }

  async function saveEdit(id) {
    setSaving(true);
    try {
      await updateDriver(id, editForm);
      onToast?.("✓", "Driver updated");
      setEditingId(null);
      load();
    } catch {
      onToast?.("⚠", "Failed to update driver");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id, name) {
    if (!confirm(`Remove ${name} from the driver list?`)) return;
    setSaving(true);
    try {
      await deleteDriver(id);
      onToast?.("✓", "Driver removed");
      if (editingId === id) cancelEdit();
      if (expandedId === id) setExpandedId(null);
      load();
    } catch {
      onToast?.("⚠", "Failed to remove driver");
    } finally {
      setSaving(false);
    }
  }

  async function handleAdd() {
    setSaving(true);
    try {
      const newDriver = await createDriver(addForm);
      onToast?.("✓", `Driver added · ${newDriver.id}`);
      setAddForm({ ...EMPTY_FORM });
      setShowAdd(false);
      load();
    } catch {
      onToast?.("⚠", "Failed to add driver");
    } finally {
      setSaving(false);
    }
  }

  function toggleExpand(id) {
    setExpandedId((prev) => prev === id ? null : id);
    if (editingId) cancelEdit();
  }

  const q = driverSearch.trim().toLowerCase();
  const filteredDrivers = q
    ? drivers.filter((d) => {
        const name = `${d.firstName || ""} ${d.lastName || ""}`.toLowerCase();
        const tractor = (d.tractor || "").toLowerCase();
        const type = (d.driverType || "").toLowerCase();
        const id = String(d.id || "");
        return name.includes(q) || tractor.includes(q) || type.includes(q) || id.includes(q);
      })
    : drivers;

  return (
    <div className="bg-navy-2 border border-subtle rounded-[14px]">
      <div className="px-[18px] py-3.5 border-b border-subtle flex items-center gap-2.5">
        <div className="text-[13.5px] font-semibold">Driver Database</div>
        <span className="text-[11px] text-txt-3 bg-navy-3 rounded-[10px] px-2 py-0.5">
          {filteredDrivers.length}{q ? ` / ${drivers.length}` : ""} drivers
        </span>
        <div className="ml-auto flex gap-2">
          <div className="relative">
            <input
              type="text"
              value={driverSearch}
              onChange={(e) => setDriverSearch(e.target.value)}
              placeholder="Search name, tractor, type..."
              className="!w-[200px] !py-1.5 !px-2.5 !text-xs"
            />
            {driverSearch && (
              <button
                onClick={() => setDriverSearch("")}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 text-txt-3 hover:text-txt-1 bg-transparent border-none cursor-pointer text-sm leading-none"
              >
                ×
              </button>
            )}
          </div>
          <button
            onClick={load}
            className="text-xs text-txt-3 hover:text-accent-2 transition-colors cursor-pointer bg-transparent border-none font-sans"
          >
            ↻ Refresh
          </button>
          <button
            onClick={() => { setShowAdd(true); cancelEdit(); setExpandedId(null); }}
            className="bg-accent text-white border-none px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer hover:bg-accent-2 transition-all font-sans"
          >
            + Add Driver
          </button>
        </div>
      </div>

      {/* Mega insurance card — shared across all F/LP/T drivers */}
      <div className="px-[18px] py-4 border-b border-subtle bg-accent/[0.04]">
        <div className="flex items-center gap-2.5 mb-3">
          <div className="text-[12px] font-semibold text-txt-1">Mega Trucking Insurance</div>
          <span className="text-[10px] text-txt-3 bg-navy-3 rounded-md px-1.5 py-0.5">
            Shared by all F / LP / T drivers
          </span>
          {!editingMega && (
            <button
              onClick={startEditMega}
              className="ml-auto bg-navy-3 border border-subtle text-txt-2 rounded-md px-2.5 py-1 text-[11px] cursor-pointer hover:bg-navy-4 hover:text-accent-2 hover:border-accent transition-all font-sans"
            >
              Edit
            </button>
          )}
        </div>

        {!editingMega ? (
          <div className="grid grid-cols-4 gap-x-6 gap-y-2 text-[12px]">
            <Detail label="Company" value={megaInsurance.insuranceCompany} />
            <Detail label="Policy #" value={megaInsurance.policyNumber} mono />
            <Detail label="Effective" value={megaInsurance.insuranceEffective} />
            <Detail label="Expiration" value={megaInsurance.insuranceExpiration} />
          </div>
        ) : (
          <div>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <Field
                label="Insurance Company"
                value={megaForm.insuranceCompany}
                onChange={(v) => setMegaForm((f) => ({ ...f, insuranceCompany: v }))}
                placeholder="e.g. Prime Property and Casualty"
              />
              <Field
                label="Policy Number"
                value={megaForm.policyNumber}
                onChange={(v) => setMegaForm((f) => ({ ...f, policyNumber: v }))}
                placeholder="e.g. PC24040671"
              />
            </div>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <Field
                label="Effective Date"
                value={megaForm.insuranceEffective}
                onChange={(v) => setMegaForm((f) => ({ ...f, insuranceEffective: v }))}
                placeholder="MM/DD/YYYY"
              />
              <Field
                label="Expiration Date"
                value={megaForm.insuranceExpiration}
                onChange={(v) => setMegaForm((f) => ({ ...f, insuranceExpiration: v }))}
                placeholder="MM/DD/YYYY"
              />
            </div>
            <div className="rounded-lg px-3.5 py-2 text-[11.5px] leading-relaxed bg-permit-orange/10 border border-permit-orange/25 text-[#FFD166] flex items-start gap-2 mb-3">
              <span className="flex-shrink-0 mt-px">⚠</span>
              <span>This will update the insurance info on every F / LP / T driver in Supabase.</span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={saveMegaInsurance}
                disabled={savingMega}
                className="bg-accent text-white border-none px-5 py-[9px] rounded-lg text-[13px] font-medium cursor-pointer hover:bg-accent-2 transition-all font-sans disabled:bg-navy-3 disabled:text-txt-3 disabled:cursor-not-allowed"
              >
                {savingMega ? "Saving..." : "Update All Mega Drivers"}
              </button>
              <button
                onClick={cancelEditMega}
                disabled={savingMega}
                className="bg-transparent border border-subtle2 text-txt-2 px-5 py-[9px] rounded-lg text-[13px] cursor-pointer hover:bg-navy-3 hover:text-txt-1 transition-all font-sans disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Add driver form */}
      {showAdd && (
        <DriverForm
          form={addForm}
          setForm={setAddForm}
          onSave={handleAdd}
          onCancel={() => { setShowAdd(false); setAddForm({ ...EMPTY_FORM }); }}
          saving={saving}
          title="Add New Driver"
        />
      )}

      {/* Driver list */}
      {loading ? (
        <div className="p-10 text-center text-txt-3 text-[13px]">Loading...</div>
      ) : filteredDrivers.length === 0 ? (
        <div className="text-center py-10 text-txt-3 text-[13px]">
          <div className="text-[32px] mb-2.5">{q ? "🔍" : "👤"}</div>
          {q ? "No drivers match your search." : "No drivers in the database."}
        </div>
      ) : (
        <table className="w-full border-collapse">
          <thead>
            <tr className="text-[11px] text-txt-3 font-medium uppercase tracking-wide bg-navy-3">
              <th className="text-left py-2.5 px-3.5 border-b border-subtle w-[60px]">ID</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle">Driver</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle w-[70px]">Type</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle w-[90px]">Tractor</th>
              <th className="text-left py-2.5 px-3.5 border-b border-subtle w-[100px]">USDOT</th>
              <th className="text-right py-2.5 px-3.5 border-b border-subtle w-[200px]">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredDrivers.map((driver) => (
              <>
                <tr key={driver.id} className="hover:bg-navy-3/50 transition-colors">
                  <td className="py-2.5 px-3.5 border-b border-subtle font-mono text-xs text-txt-3">{driver.id}</td>
                  <td className="py-2.5 px-3.5 border-b border-subtle">
                    <div className="flex items-center gap-[7px]">
                      <div className="w-6 h-6 rounded-full bg-steel flex items-center justify-center text-[9px] font-semibold text-accent-2 flex-shrink-0">
                        {(driver.firstName || "")[0]}{(driver.lastName || "")[0]}
                      </div>
                      <span className="text-[13px]">{driver.firstName} {driver.lastName}</span>
                    </div>
                  </td>
                  <td className="py-2.5 px-3.5 border-b border-subtle">
                    <span className={`inline-flex items-center px-2 py-[3px] rounded-md text-[11px] font-medium ${
                      isCompanyType(driver.driverType) ? "bg-accent/15 text-accent-2" : "bg-gold/15 text-gold-2"
                    }`}>
                      {driver.driverType}
                    </span>
                  </td>
                  <td className="py-2.5 px-3.5 border-b border-subtle font-mono text-[13px] text-txt-2">{driver.tractor}</td>
                  <td className="py-2.5 px-3.5 border-b border-subtle font-mono text-[12px] text-txt-3">{driver.usdot}</td>
                  <td className="py-2.5 px-3.5 border-b border-subtle text-right">
                    <div className="flex justify-end gap-1.5">
                      <button
                        onClick={() => toggleExpand(driver.id)}
                        className="bg-navy-3 border border-subtle text-txt-2 rounded-md px-2.5 py-1 text-[11px] cursor-pointer hover:bg-navy-4 hover:text-txt-1 transition-all font-sans"
                      >
                        {expandedId === driver.id ? "Hide" : "Details"}
                      </button>
                      <button
                        onClick={() => startEdit(driver)}
                        className="bg-navy-3 border border-subtle text-txt-2 rounded-md px-2.5 py-1 text-[11px] cursor-pointer hover:bg-navy-4 hover:text-accent-2 hover:border-accent transition-all font-sans"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(driver.id, `${driver.firstName} ${driver.lastName}`)}
                        className="bg-permit-red/10 border border-permit-red/20 text-permit-red2 rounded-md px-2.5 py-1 text-[11px] cursor-pointer hover:bg-permit-red/20 transition-all font-sans"
                      >
                        Remove
                      </button>
                    </div>
                  </td>
                </tr>

                {/* Expanded details row */}
                {expandedId === driver.id && editingId !== driver.id && (
                  <tr key={`${driver.id}-detail`}>
                    <td colSpan={6} className="border-b border-subtle bg-navy-3/30 px-3.5 py-4">
                      <div className="grid grid-cols-4 gap-x-6 gap-y-3 text-[12px]">
                        <Detail label="Year" value={driver.year} />
                        <Detail label="Make" value={driver.make} />
                        <Detail label="VIN" value={driver.vin} mono />
                        <Detail label="Tag" value={`${driver.tagNumber} (${driver.tagState})`} />
                        <Detail label="USDOT" value={driver.usdot} mono />
                        {!isCompanyType(driver.driverType) && <Detail label="FEIN" value={driver.fein} mono />}
                        <Detail label="Insurance" value={driver.insuranceCompany} />
                        <Detail label="Policy #" value={driver.policyNumber} mono />
                        <Detail label="Ins. Effective" value={driver.insuranceEffective} />
                        <Detail label="Ins. Expiration" value={driver.insuranceExpiration} />
                      </div>
                    </td>
                  </tr>
                )}

                {/* Edit form row */}
                {editingId === driver.id && (
                  <tr key={`${driver.id}-edit`}>
                    <td colSpan={6} className="border-b border-subtle p-0">
                      <DriverForm
                        form={editForm}
                        setForm={setEditForm}
                        onSave={() => saveEdit(driver.id)}
                        onCancel={cancelEdit}
                        saving={saving}
                        title={`Edit — ${driver.firstName} ${driver.lastName}`}
                      />
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Detail({ label, value, mono }) {
  return (
    <div>
      <div className="text-[10px] text-txt-3 uppercase tracking-wide font-medium mb-0.5">{label}</div>
      <div className={`text-txt-1 ${mono ? "font-mono" : ""}`}>{value || "—"}</div>
    </div>
  );
}
