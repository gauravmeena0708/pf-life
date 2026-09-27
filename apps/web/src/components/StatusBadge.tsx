/** Status shown as text and shape, never colour alone (init.md §9 accessibility). */
const STYLES: Record<string, { label: string; symbol: string; className: string }> = {
  W: { label: "Working", symbol: "●", className: "badge badge-working" },
  Working: { label: "Working", symbol: "●", className: "badge badge-working" },
  M: { label: "Mock", symbol: "◆", className: "badge badge-mock" },
  Mock: { label: "Mock", symbol: "◆", className: "badge badge-mock" },
  P: { label: "Planned", symbol: "○", className: "badge badge-planned" },
  Planned: { label: "Planned", symbol: "○", className: "badge badge-planned" },
  "?": { label: "Definition pending", symbol: "?", className: "badge badge-pending" },
};

export function StatusBadge({ status }: { status: string }) {
  const s = STYLES[status] ?? { label: status, symbol: "·", className: "badge" };
  return (
    <span className={s.className}>
      <span aria-hidden="true">{s.symbol}</span> {s.label}
    </span>
  );
}
