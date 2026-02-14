export function formatCurrency(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_000_000) {
    return `${sign}$${(abs / 1_000_000).toFixed(2)}M`;
  }
  if (abs >= 1_000) {
    return `${sign}$${abs.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  return `${sign}$${abs.toFixed(2)}`;
}

export function formatPct(value: number, decimals = 2): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

export function formatPctRaw(value: number, decimals = 2): string {
  return `${value.toFixed(decimals)}%`;
}

export function formatR(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(3)}R`;
}

export function formatNumber(value: number, decimals = 2): string {
  return value.toFixed(decimals);
}

export function pnlColor(value: number): string {
  if (value > 0) return "var(--color-profit)";
  if (value < 0) return "var(--color-loss)";
  return "var(--color-text-secondary)";
}
