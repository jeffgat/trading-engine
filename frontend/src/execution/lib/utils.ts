import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import type { TradeLogEntry, ExecTradeContext } from "@/execution/lib/types"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export const CHARTABLE_EVENTS = new Set([
  "FILLED", "SL_HIT", "TP2_HIT", "TP2_DIRECT", "TP1_PARTIAL", "TP1_BE_SINGLE", "TP1_SINGLE_EXIT", "BE_HIT", "EOD_FLAT",
]);

export function parseSessionName(session: string): { instrument: string; sessionLabel: string } {
  // Strip known suffixes like "_LSI", "_CONT"
  const cleaned = session.replace(/_(LSI|CONT)$/i, "");
  const parts = cleaned.split("_");
  return {
    instrument: parts[0] ?? session,
    sessionLabel: parts.slice(1).join("_") || "NY",
  };
}

export function resolveTradeContext(
  clicked: TradeLogEntry,
  allEntries: TradeLogEntry[],
  clickedIdx: number,
): ExecTradeContext | null {
  // Find the FILLED event - either the clicked entry itself or search for matching FILLED
  let filledEntry: TradeLogEntry | null = null;
  let filledIdx = clickedIdx;

  if (clicked.event === "FILLED") {
    filledEntry = clicked;
  } else {
    // For exit events, search for the FILLED event with the same session
    // Entries are newest-first, so FILLED for this trade is AFTER the exit in the array
    for (let i = clickedIdx + 1; i < allEntries.length; i++) {
      if (allEntries[i].event === "FILLED" && allEntries[i].session === clicked.session) {
        filledEntry = allEntries[i];
        filledIdx = i;
        break;
      }
    }
  }

  if (!filledEntry) return null;

  const d = filledEntry.details;
  let entry = parseFloat(d.entry ?? d.price ?? "");
  let stop = parseFloat(d.stop ?? "");
  let tp1 = parseFloat(d.tp1 ?? "");
  let tp2 = parseFloat(d.tp2 ?? "");
  const dirRaw = d.direction ?? d.dir ?? "";
  let direction: "long" | "short" = dirRaw === "-1" || dirRaw.toLowerCase() === "short" ? "short" : "long";

  // Fallback: older continuation engine FILLED events only have dir+entry.
  // Search for the preceding LONG_SETUP/SHORT_SETUP event to get stop/tp1/tp2.
  if (isNaN(stop) || isNaN(tp1) || isNaN(tp2)) {
    const filledDate = filledEntry.timestamp.split(" ")[0];
    for (let i = filledIdx + 1; i < allEntries.length; i++) {
      const ev = allEntries[i];
      // Stop searching once we cross into a prior date
      if (!ev.timestamp.startsWith(filledDate)) break;
      if ((ev.event === "LONG_SETUP" || ev.event === "SHORT_SETUP") && ev.session === filledEntry.session) {
        if (isNaN(entry)) entry = parseFloat(ev.details.entry ?? "");
        if (isNaN(stop)) stop = parseFloat(ev.details.stop ?? "");
        if (isNaN(tp1)) tp1 = parseFloat(ev.details.tp1 ?? "");
        if (isNaN(tp2)) tp2 = parseFloat(ev.details.tp2 ?? "");
        // Derive direction from the SETUP event name
        direction = ev.event === "SHORT_SETUP" ? "short" : "long";
        break;
      }
    }
  }

  if (isNaN(entry) || isNaN(stop) || isNaN(tp1) || isNaN(tp2)) return null;

  const { instrument, sessionLabel } = parseSessionName(filledEntry.session);

  // Extract date from FILLED timestamp (YYYY-MM-DD)
  const date = filledEntry.timestamp.split(" ")[0] ?? "";
  if (!date) return null;

  return { instrument, session: sessionLabel, date, direction, entry, stop, tp1, tp2 };
}
