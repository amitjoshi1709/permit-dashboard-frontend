const STYLES = {
  // Permit types — distinct colors
  ITP:       "bg-blue-100 text-blue-800 border-blue-300",
  MFTP:      "bg-purple-100 text-purple-800 border-purple-300",
  trip:      "bg-blue-100 text-blue-800 border-blue-300",
  fuel:      "bg-purple-100 text-purple-800 border-purple-300",
  trip_fuel: "bg-indigo-100 text-indigo-800 border-indigo-300",
  os_ow:     "bg-orange-100 text-orange-800 border-orange-300",
  fl_blanket_bulk:         "bg-teal-100 text-teal-800 border-teal-300",
  fl_blanket_inner_bridge: "bg-cyan-100 text-cyan-800 border-cyan-300",
  fl_blanket_flatbed:      "bg-sky-100 text-sky-800 border-sky-300",
  al_annual_osow:          "bg-orange-100 text-orange-800 border-orange-300",
  // Statuses
  Active:  "bg-green-100 text-green-800 border-green-300",
  Expired: "bg-red-100 text-red-800 border-red-300",
  Pending: "bg-yellow-100 text-yellow-800 border-yellow-300",
  issued:  "bg-green-100 text-green-800 border-green-300",
  success: "bg-green-100 text-green-800 border-green-300",
  failed:  "bg-red-100 text-red-800 border-red-300",
  pending: "bg-yellow-100 text-yellow-800 border-yellow-300",
  error:   "bg-red-100 text-red-800 border-red-300",
};

const LABELS = {
  ITP: "Trip",
  MFTP: "Fuel",
  trip: "Trip",
  fuel: "Fuel",
  trip_fuel: "Trip + Fuel",
  os_ow: "OS/OW",
  fl_blanket_bulk: "FL Bulk",
  fl_blanket_inner_bridge: "FL Inner Bridge",
  fl_blanket_flatbed: "FL Flatbed",
  al_annual_osow: "AL Annual OS/OW",
};

export default function Badge({ type }) {
  const cls = STYLES[type] || "bg-stone-100 text-ink-500 border-ink/15";
  const label = LABELS[type] || type;
  return (
    <span
      className={`inline-flex items-center px-2.5 py-1 rounded-sm text-[10px] font-semibold uppercase tracking-[0.06em] border ${cls}`}
    >
      {label}
    </span>
  );
}
