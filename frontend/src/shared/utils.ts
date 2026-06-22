import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function moneyColor(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "var(--color-text-secondary)";
  if (value > 0) return "var(--color-money-positive)";
  if (value < 0) return "var(--color-money-negative)";
  return "var(--color-text-secondary)";
}

export function moneyTextClass(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "text-text-muted";
  if (value > 0) return "text-money-positive";
  if (value < 0) return "text-money-negative";
  return "text-text-secondary";
}
