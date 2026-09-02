import { RISK } from "@/lib/ui";

export function RiskBadge({ level }) {
  const r = RISK[level] || RISK.medium;
  return (
    <span
      data-testid={`risk-badge-${level}`}
      className={`inline-flex items-center text-xs font-semibold px-2.5 py-0.5 rounded-full border ${r.cls}`}
    >
      {r.label}
    </span>
  );
}
