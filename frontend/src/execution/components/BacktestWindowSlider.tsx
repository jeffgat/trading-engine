import { useMemo, useCallback, useRef } from "react";
import { DatePicker } from "@/shared/ui/date-picker";

interface BacktestWindowSliderProps {
  startDate: string;
  originalStart: string;
  originalEnd: string;
  onChange: (start: string, end: string) => void;
  onReset: () => void;
}

function dateToDays(d: string): number {
  return Math.floor(new Date(d + "T00:00:00").getTime() / 86_400_000);
}

function daysToDate(days: number): string {
  return new Date(days * 86_400_000).toISOString().slice(0, 10);
}

function snapToWeek(day: number, minDay: number): number {
  return minDay + Math.round((day - minDay) / 7) * 7;
}

const DAYS_1Y = 52 * 7;
const DAYS_2Y = 104 * 7;
const DAYS_5Y = 260 * 7;

export function BacktestWindowSlider({
  startDate,
  originalStart,
  originalEnd,
  onChange,
  onReset,
}: BacktestWindowSliderProps) {
  const isFiltered = startDate !== originalStart;

  const minDay = useMemo(() => dateToDays(originalStart), [originalStart]);
  const maxDay = useMemo(() => dateToDays(originalEnd), [originalEnd]);
  const startDay = useMemo(() => dateToDays(startDate), [startDate]);

  const totalDays = maxDay - minDay;
  const hasRange = originalStart && originalEnd && totalDays > 0;

  const leftPct = hasRange ? ((startDay - minDay) / totalDays) * 100 : 0;

  const trackRef = useRef<HTMLDivElement>(null);
  const dragging = useRef<boolean>(false);

  const dayFromPointer = useCallback(
    (clientX: number) => {
      const track = trackRef.current;
      if (!track) return minDay;
      const rect = track.getBoundingClientRect();
      const pct = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      const raw = minDay + pct * totalDays;
      return snapToWeek(Math.round(raw), minDay);
    },
    [minDay, totalDays],
  );

  const onThumbPointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      dragging.current = true;
    },
    [],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragging.current) return;
      const day = dayFromPointer(e.clientX);
      const clamped = Math.min(day, maxDay - 7);
      onChange(daysToDate(Math.max(clamped, minDay)), originalEnd);
    },
    [dayFromPointer, minDay, maxDay, originalEnd, onChange],
  );

  const onPointerUp = useCallback(() => {
    dragging.current = false;
  }, []);

  /** Set the start date to a fixed span back from today. */
  const setSpan = useCallback(
    (spanDays: number) => {
      const newStart = Math.max(minDay, maxDay - spanDays);
      onChange(daysToDate(snapToWeek(newStart, minDay)), originalEnd);
    },
    [minDay, maxDay, originalEnd, onChange],
  );

  if (!hasRange) return null;

  return (
    <div className="space-y-2">
      {/* Date picker + presets row */}
      <div className="flex items-center gap-2">
        <span className="text-[11px] text-text-muted font-medium uppercase tracking-wide">From</span>
        <DatePicker
          value={startDate}
          onChange={(v) => v && onChange(v, originalEnd)}
          placeholder="Start date"
        />
        <span className="text-text-muted text-xs">{"\u2013"}</span>
        <span className="text-xs text-text-secondary">Today</span>
        {isFiltered && (
          <button
            onClick={onReset}
            className="rounded border border-border px-2 py-0.5 text-[10px] text-text-muted transition-colors hover:border-text-muted hover:text-text-secondary"
          >
            Reset
          </button>
        )}
        <div className="mx-1 h-3 w-px bg-border" />
        <PresetBtn label="All" onClick={onReset} />
        <PresetBtn label="1Y" onClick={() => setSpan(DAYS_1Y)} />
        <PresetBtn label="2Y" onClick={() => setSpan(DAYS_2Y)} />
        <PresetBtn label="5Y" onClick={() => setSpan(DAYS_5Y)} />
      </div>

      {/* Range slider — left thumb only, right pinned to today */}
      <div
        ref={trackRef}
        className="relative h-5 select-none touch-none"
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
      >
        <div className="absolute top-1/2 left-0 right-0 h-1 -translate-y-1/2 rounded-full bg-border" />
        {/* Active range fill */}
        <div
          className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-accent/50"
          style={{ left: `${leftPct}%`, right: "0%" }}
        />
        {/* Left thumb */}
        <div
          className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 cursor-grab rounded-full border-2 border-accent bg-bg-card active:cursor-grabbing active:bg-accent"
          style={{ left: `${leftPct}%` }}
          onPointerDown={onThumbPointerDown}
        />
        {/* Right end — fixed dot */}
        <div
          className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent/70"
          style={{ left: "100%" }}
        />
      </div>
    </div>
  );
}

function PresetBtn({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-text-muted transition-colors hover:border-text-muted hover:text-text-secondary"
    >
      {label}
    </button>
  );
}
