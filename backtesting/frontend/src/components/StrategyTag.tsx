const STRATEGY_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  continuation: { bg: "rgba(34, 197, 94, 0.15)", text: "rgb(34, 197, 94)", label: "ORB-C" },
  reversal: { bg: "rgba(168, 85, 247, 0.15)", text: "rgb(168, 85, 247)", label: "ORB-R" },
};

const DEFAULT = { bg: "rgba(34, 197, 94, 0.15)", text: "rgb(34, 197, 94)", label: "ORB-C" };

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
