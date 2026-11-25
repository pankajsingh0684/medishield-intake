import type { Case, DecisionKind } from "@/lib/types";

type Label = { icon: string; text: string; color: string };

export function statusLabel(
  item: Pick<Case, "status"> & { effective_decision?: DecisionKind | null },
): Label {
  if (
    [
      "RECEIVED",
      "CLASSIFIED",
      "PROCESSING",
      "FRAUD_CHECK",
      "AGGREGATED",
    ].includes(item.status)
  )
    return {
      icon: "◷",
      text: "Processing",
      color: "border-blue-700 bg-blue-50 text-blue-900",
    };
  const decision = item.effective_decision;
  if (decision === "APPROVE")
    return {
      icon: "✓",
      text: "Approved",
      color: "border-green-700 bg-green-50 text-green-900",
    };
  if (decision === "REJECT")
    return {
      icon: "×",
      text: "Rejected",
      color: "border-red-700 bg-red-50 text-red-900",
    };
  if (
    item.status === "FAILED" ||
    item.status === "NEEDS_REVIEW" ||
    decision === "ESCALATE"
  )
    return {
      icon: "!",
      text: "Escalated",
      color: "border-amber-700 bg-amber-50 text-amber-950",
    };
  return {
    icon: "•",
    text: item.status.replaceAll("_", " "),
    color: "border-slate-600 bg-slate-50 text-slate-900",
  };
}

export function StatusBadge({
  item,
}: {
  item: Parameters<typeof statusLabel>[0];
}) {
  const value = statusLabel(item);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-xs font-semibold ${value.color}`}
    >
      <span aria-hidden="true">{value.icon}</span>
      {value.text}
    </span>
  );
}
