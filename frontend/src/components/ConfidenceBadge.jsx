import { CONFIDENCE } from "@/lib/ui";

export function ConfidenceBadge({ score }) {
  const c = CONFIDENCE[score] || CONFIDENCE.unreachable;
  return (
    <span
      data-testid={`confidence-badge-${score || "unreachable"}`}
      className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full border ${c.cls}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  );
}
