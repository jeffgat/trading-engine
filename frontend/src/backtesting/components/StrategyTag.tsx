const STRATEGY_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  continuation: { bg: "rgba(52, 211, 153, 0.1)", text: "rgb(52, 211, 153)", label: "ORB-C" },
  reversal: { bg: "rgba(52, 211, 153, 0.1)", text: "rgb(52, 211, 153)", label: "ORB-R" },
  inversion: { bg: "rgba(52, 211, 153, 0.1)", text: "rgb(52, 211, 153)", label: "INV" },
  cisd: { bg: "rgba(52, 211, 153, 0.1)", text: "rgb(52, 211, 153)", label: "CISD" },
  lsi: { bg: "rgba(167, 139, 250, 0.1)", text: "rgb(167, 139, 250)", label: "LSI" },
  ib: { bg: "rgba(251, 191, 36, 0.1)", text: "rgb(251, 191, 36)", label: "IB" },
};

const DEFAULT = { bg: "rgba(107, 114, 128, 0.15)", text: "rgb(107, 114, 128)", label: "???" };

export function StrategyTag({ strategy }: { strategy?: string }) {
  const s = STRATEGY_STYLES[strategy ?? "continuation"] ?? DEFAULT;

  return (
    <span
      className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
      style={{ backgroundColor: s.bg, color: s.text }}
    >
      {s.label}
    </span>
  );
}
