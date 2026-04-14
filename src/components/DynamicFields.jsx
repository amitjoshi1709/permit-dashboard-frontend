import { useMemo } from "react";

/**
 * Generic schema-driven form renderer.
 *
 * Props:
 *   fields   — array of field definitions from GET /api/permits/form-fields
 *   values   — current field values (flat object keyed by field.key)
 *   onChange — (key, value) => void
 *   disabled — boolean
 */
export default function DynamicFields({ fields, values, onChange, disabled }) {
  // Group fields by their `group` property, preserving order
  const groups = useMemo(() => {
    const map = new Map();
    for (const field of fields) {
      const g = field.group || "Additional Fields";
      if (!map.has(g)) map.set(g, []);
      map.get(g).push(field);
    }
    return [...map.entries()]; // [[groupName, fields[]], ...]
  }, [fields]);

  if (fields.length === 0) return null;

  return (
    <div className="space-y-4 p-4 rounded-lg border border-accent/25 bg-accent/5">
      {groups.map(([groupName, groupFields]) => (
        <div key={groupName}>
          <div className="text-[11px] font-medium uppercase tracking-wide text-accent-2 mb-2">
            {groupName}
          </div>
          <div className="grid grid-cols-2 gap-3">
            {groupFields.map((field) => (
              <FieldRenderer
                key={field.key}
                field={field}
                value={values[field.key]}
                allValues={values}
                onChange={onChange}
                disabled={disabled}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function FieldRenderer({ field, value, allValues, onChange, disabled }) {
  const { key, label, type, placeholder, options, dependsOn } = field;

  // ── text / number ──
  if (type === "text" || type === "number") {
    return (
      <div>
        <label className="block text-[10px] text-txt-3 mb-1">{label}</label>
        <input
          type={type}
          placeholder={placeholder || ""}
          value={value || ""}
          onChange={(e) => onChange(key, e.target.value)}
          disabled={disabled}
        />
      </div>
    );
  }

  // ── select ──
  if (type === "select") {
    return (
      <div>
        <label className="block text-[10px] text-txt-3 mb-1">{label}</label>
        <select
          value={value || ""}
          onChange={(e) => onChange(key, e.target.value)}
          disabled={disabled}
        >
          <option value="">-- Select --</option>
          {(options || []).map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    );
  }

  // ── textarea ──
  if (type === "textarea") {
    return (
      <div className="col-span-2">
        <label className="block text-[10px] text-txt-3 mb-1">{label}</label>
        <textarea
          placeholder={placeholder || ""}
          value={value || ""}
          onChange={(e) => onChange(key, e.target.value)}
          disabled={disabled}
          rows={3}
          className="w-full bg-navy-3 border border-subtle text-txt-1 rounded-lg px-3 py-2 text-[13px] resize-none focus:border-accent/50 focus:outline-none transition-colors"
        />
      </div>
    );
  }

  // ── boolean (Yes / No toggle) ──
  if (type === "boolean") {
    const current = value === true || value === "yes";
    return (
      <div>
        <label className="block text-[10px] text-txt-3 mb-1">{label}</label>
        <div className="flex gap-2">
          {["Yes", "No"].map((opt) => {
            const isActive = opt === "Yes" ? current : value === false || value === "no";
            return (
              <button
                key={opt}
                type="button"
                onClick={() => onChange(key, opt === "Yes" ? "yes" : "no")}
                disabled={disabled}
                className={`flex-1 py-2 rounded-lg text-xs font-medium border transition-colors cursor-pointer ${
                  isActive
                    ? "bg-accent/15 border-accent/40 text-accent-2"
                    : "bg-navy-3 border-subtle text-txt-2 hover:border-subtle2"
                } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
              >
                {opt}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  // ── dimension_ft_in (two compact inputs side by side) ──
  if (type === "dimension_ft_in") {
    const val = value || { ft: "", in: "" };
    return (
      <div>
        <label className="block text-[10px] text-txt-3 mb-1">{label}</label>
        <div className="flex items-center gap-1.5">
          <input
            type="number"
            min="0"
            placeholder="0"
            value={val.ft || ""}
            onChange={(e) => onChange(key, { ...val, ft: e.target.value })}
            disabled={disabled}
            className="w-16 bg-navy-3 border border-subtle text-txt-1 rounded-md px-2 py-1.5 text-[12px] text-center focus:border-accent/50 focus:outline-none transition-colors [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
          />
          <span className="text-[10px] text-txt-3 font-medium">ft</span>
          <input
            type="number"
            min="0"
            max="11"
            placeholder="0"
            value={val.in || ""}
            onChange={(e) => onChange(key, { ...val, in: e.target.value })}
            disabled={disabled}
            className="w-14 bg-navy-3 border border-subtle text-txt-1 rounded-md px-2 py-1.5 text-[12px] text-center focus:border-accent/50 focus:outline-none transition-colors [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
          />
          <span className="text-[10px] text-txt-3 font-medium">in</span>
        </div>
      </div>
    );
  }

  // ── axle_group (dynamic spacing inputs based on axleCount) ──
  if (type === "axle_group") {
    const countKey = dependsOn || "axleCount";
    const count = parseInt(allValues[countKey]) || 0;
    const spacingCount = Math.max(0, count - 1);
    const spacings = Array.isArray(value) ? value : [];

    if (spacingCount === 0) return null;

    return (
      <div className="col-span-2">
        <label className="block text-[10px] text-txt-3 mb-1">{label}</label>
        <div className="grid grid-cols-2 gap-3">
          {Array.from({ length: spacingCount }, (_, i) => {
            const pair = (spacings[i] && typeof spacings[i] === "object") ? spacings[i] : { ft: "", in: "" };
            const updatePair = (next) => {
              const updated = [...spacings];
              while (updated.length < spacingCount) updated.push({ ft: "", in: "" });
              updated[i] = next;
              onChange(key, updated.slice(0, spacingCount));
            };
            return (
              <div key={i}>
                <label className="block text-[10px] text-txt-3 mb-1">
                  Axle {i + 1} → {i + 2}
                </label>
                <div className="flex items-center gap-1.5">
                  <input
                    type="number"
                    min="0"
                    placeholder="0"
                    value={pair.ft || ""}
                    onChange={(e) => updatePair({ ...pair, ft: e.target.value })}
                    disabled={disabled}
                    className="w-16 bg-navy-3 border border-subtle text-txt-1 rounded-md px-2 py-1.5 text-[12px] text-center focus:border-accent/50 focus:outline-none transition-colors [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                  />
                  <span className="text-[10px] text-txt-3 font-medium">ft</span>
                  <input
                    type="number"
                    min="0"
                    max="11"
                    placeholder="0"
                    value={pair.in || ""}
                    onChange={(e) => updatePair({ ...pair, in: e.target.value })}
                    disabled={disabled}
                    className="w-14 bg-navy-3 border border-subtle text-txt-1 rounded-md px-2 py-1.5 text-[12px] text-center focus:border-accent/50 focus:outline-none transition-colors [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                  />
                  <span className="text-[10px] text-txt-3 font-medium">in</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // ── axle_weight_group (weight per axle based on axleCount) ──
  if (type === "axle_weight_group") {
    const countKey = dependsOn || "axleCount";
    const count = parseInt(allValues[countKey]) || 0;
    const weights = Array.isArray(value) ? value : [];

    if (count === 0) return null;

    return (
      <div className="col-span-2">
        <label className="block text-[10px] text-txt-3 mb-1">{label}</label>
        <div className="grid grid-cols-2 gap-3">
          {Array.from({ length: count }, (_, i) => (
            <div key={i}>
              <label className="block text-[10px] text-txt-3 mb-1">
                Axle {i + 1}
              </label>
              <input
                type="number"
                min="0"
                placeholder="lbs"
                value={weights[i] || ""}
                onChange={(e) => {
                  const updated = [...weights];
                  while (updated.length < count) updated.push("");
                  updated[i] = e.target.value;
                  onChange(key, updated.slice(0, count));
                }}
                disabled={disabled}
              />
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Fallback — unknown type, render as text
  return (
    <div>
      <label className="block text-[10px] text-txt-3 mb-1">{label}</label>
      <input
        type="text"
        placeholder={placeholder || ""}
        value={value || ""}
        onChange={(e) => onChange(key, e.target.value)}
        disabled={disabled}
      />
    </div>
  );
}
