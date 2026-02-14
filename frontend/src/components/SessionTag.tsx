const SESSION_COLORS: Record<string, { bg: string; text: string }> = {
  NY: { bg: "rgba(96, 165, 250, 0.15)", text: "rgb(96, 165, 250)" },
  ASIA: { bg: "rgba(248, 113, 113, 0.15)", text: "rgb(248, 113, 113)" },
  LDN: { bg: "rgba(251, 191, 36, 0.15)", text: "rgb(251, 191, 36)" },
};

const DEFAULT_COLOR = { bg: "var(--color-bg-secondary)", text: "var(--color-text-muted)" };

export function SessionTag({ session }: { session: string }) {
  const colors = SESSION_COLORS[session.toUpperCase()] ?? DEFAULT_COLOR;

  return (
    <span
      className="rounded px-1.5 py-0.5 text-[10px] font-medium"
      style={{ backgroundColor: colors.bg, color: colors.text }}
    >
      {session}
    </span>
  );
}
