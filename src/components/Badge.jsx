const STYLES = {
  ITP: "bg-accent/15 text-accent-2",
  MFTP: "bg-gold/15 text-gold-2",
  Active: "bg-permit-green/15 text-[#3EDB7A]",
  Expired: "bg-permit-red/15 text-permit-red2",
  Pending: "bg-permit-orange/15 text-[#FFD166]",
  issued: "bg-permit-green/15 text-[#3EDB7A]",
  failed: "bg-permit-red/15 text-permit-red2",
  pending: "bg-permit-orange/15 text-[#FFD166]",
};

export default function Badge({ type }) {
  const cls = STYLES[type] || "bg-steel/30 text-txt-2";
  return (
    <span className={`inline-flex items-center px-2 py-[3px] rounded-md text-[11px] font-medium ${cls}`}>
      {type === "ITP" ? "ITP Trip" : type === "MFTP" ? "MFTP Fuel" : type}
    </span>
  );
}
