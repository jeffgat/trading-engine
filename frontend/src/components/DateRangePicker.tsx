import { useMemo, useCallback, useRef } from 'react';

interface DateRangePickerProps {
    startDate: string;
    endDate: string;
    originalStart: string;
    originalEnd: string;
    onChange: (start: string, end: string) => void;
    onReset: () => void;
    loading: boolean;
    disabled: boolean;
}

/** Convert YYYY-MM-DD to days since epoch. */
function dateToDays(d: string): number {
    return Math.floor(new Date(d + 'T00:00:00').getTime() / 86_400_000);
}

/** Convert days since epoch to YYYY-MM-DD. */
function daysToDate(days: number): string {
    return new Date(days * 86_400_000).toISOString().slice(0, 10);
}

/** Snap a day value to the nearest week tick. */
function snapToWeek(day: number, minDay: number): number {
    return minDay + Math.round((day - minDay) / 7) * 7;
}

const DAYS_1Y = 52 * 7; // ~364 days
const DAYS_2Y = 104 * 7; // ~728 days

export function DateRangePicker({
    startDate,
    endDate,
    originalStart,
    originalEnd,
    onChange,
    onReset,
    loading,
    disabled,
}: DateRangePickerProps) {
    const isFiltered = startDate !== originalStart || endDate !== originalEnd;

    const minDay = useMemo(() => dateToDays(originalStart), [originalStart]);
    const maxDay = useMemo(() => dateToDays(originalEnd), [originalEnd]);
    const startDay = useMemo(() => dateToDays(startDate), [startDate]);
    const endDay = useMemo(() => dateToDays(endDate), [endDate]);

    const totalWeeks = Math.max(1, Math.floor((maxDay - minDay) / 7));
    const hasRange = originalStart && originalEnd && totalWeeks > 0;

    // Percentages for the filled track segment
    const leftPct = hasRange ? ((startDay - minDay) / (maxDay - minDay)) * 100 : 0;
    const rightPct = hasRange ? ((maxDay - endDay) / (maxDay - minDay)) * 100 : 0;

    const trackRef = useRef<HTMLDivElement>(null);
    const dragging = useRef<'start' | 'end' | 'window' | null>(null);
    const dragOffset = useRef(0);

    const dayFromPointer = useCallback(
        (clientX: number) => {
            const track = trackRef.current;
            if (!track) return minDay;
            const rect = track.getBoundingClientRect();
            const pct = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
            const raw = minDay + pct * (maxDay - minDay);
            return snapToWeek(Math.round(raw), minDay);
        },
        [minDay, maxDay],
    );

    const onPointerDown = useCallback(
        (thumb: 'start' | 'end') => (e: React.PointerEvent) => {
            if (disabled) return;
            e.preventDefault();
            e.stopPropagation();
            (e.target as HTMLElement).setPointerCapture(e.pointerId);
            dragging.current = thumb;
        },
        [disabled],
    );

    const onWindowPointerDown = useCallback(
        (e: React.PointerEvent) => {
            if (disabled) return;
            e.preventDefault();
            (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
            dragging.current = 'window';
            dragOffset.current = dayFromPointer(e.clientX) - startDay;
        },
        [disabled, dayFromPointer, startDay],
    );

    const onPointerMove = useCallback(
        (e: React.PointerEvent) => {
            if (!dragging.current) return;
            const day = dayFromPointer(e.clientX);
            if (dragging.current === 'start') {
                const clamped = Math.min(day, endDay - 7);
                onChange(daysToDate(Math.max(clamped, minDay)), endDate);
            } else if (dragging.current === 'end') {
                const clamped = Math.max(day, startDay + 7);
                onChange(startDate, daysToDate(Math.min(clamped, maxDay)));
            } else if (dragging.current === 'window') {
                const span = endDay - startDay;
                let newStart = snapToWeek(Math.round(day - dragOffset.current), minDay);
                newStart = Math.max(minDay, Math.min(newStart, maxDay - span));
                const newEnd = newStart + span;
                onChange(daysToDate(newStart), daysToDate(newEnd));
            }
        },
        [dayFromPointer, startDay, endDay, minDay, maxDay, startDate, endDate, onChange],
    );

    const onPointerUp = useCallback(() => {
        dragging.current = null;
    }, []);

    /** Set the window to a fixed span ending at the current endDay. */
    const setSpan = useCallback(
        (spanDays: number) => {
            const newStart = Math.max(minDay, endDay - spanDays);
            onChange(daysToDate(snapToWeek(newStart, minDay)), endDate);
        },
        [minDay, endDay, endDate, onChange],
    );

    /** Shift the entire window by deltaDays, clamping to bounds. */
    const shiftWindow = useCallback(
        (deltaDays: number) => {
            const span = endDay - startDay;
            let newStart = startDay + deltaDays;
            newStart = snapToWeek(Math.max(minDay, Math.min(newStart, maxDay - span)), minDay);
            const newEnd = Math.min(newStart + span, maxDay);
            onChange(daysToDate(newStart), daysToDate(newEnd));
        },
        [startDay, endDay, minDay, maxDay, onChange],
    );

    return (
        <div className="space-y-2">
            {/* Date inputs row */}
            <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                    <label className="text-xs text-text-muted">From</label>
                    <input
                        type="date"
                        value={startDate}
                        min={originalStart}
                        max={endDate || originalEnd}
                        onChange={(e) => onChange(e.target.value, endDate)}
                        disabled={disabled}
                        className="rounded border border-border bg-bg-card px-2 py-1 text-xs text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
                    />
                </div>
                <div className="flex items-center gap-2">
                    <label className="text-xs text-text-muted">To</label>
                    <input
                        type="date"
                        value={endDate}
                        min={startDate || originalStart}
                        max={originalEnd}
                        onChange={(e) => onChange(startDate, e.target.value)}
                        disabled={disabled}
                        className="rounded border border-border bg-bg-card px-2 py-1 text-xs text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
                    />
                </div>
                {isFiltered && !disabled && (
                    <button
                        onClick={onReset}
                        disabled={loading}
                        className="rounded border border-border px-2 py-1 text-xs text-text-muted transition-colors hover:border-text-muted hover:text-text-secondary disabled:opacity-40"
                    >
                        Reset
                    </button>
                )}
                {loading && (
                    <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-border border-t-accent" />
                )}
                {disabled && (
                    <span className="text-xs text-text-muted">(trade data required)</span>
                )}
            </div>

            {/* Range slider */}
            {hasRange && !disabled && (
                <div
                    ref={trackRef}
                    className="relative h-5 select-none touch-none"
                    onPointerMove={onPointerMove}
                    onPointerUp={onPointerUp}
                    onPointerLeave={onPointerUp}
                >
                    {/* Track background */}
                    <div className="absolute top-1/2 left-0 right-0 h-1 -translate-y-1/2 rounded-full bg-border" />
                    {/* Active range fill — draggable to slide window */}
                    <div
                        className="absolute top-1/2 h-3 -translate-y-1/2 cursor-grab rounded-full bg-accent/50 hover:bg-accent/70 active:cursor-grabbing active:bg-accent/70"
                        style={{ left: `${leftPct}%`, right: `${rightPct}%` }}
                        onPointerDown={onWindowPointerDown}
                    />
                    {/* Start thumb */}
                    <div
                        className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 cursor-grab rounded-full border-2 border-accent bg-bg-card active:cursor-grabbing active:bg-accent"
                        style={{ left: `${leftPct}%` }}
                        onPointerDown={onPointerDown('start')}
                    />
                    {/* End thumb */}
                    <div
                        className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 cursor-grab rounded-full border-2 border-accent bg-bg-card active:cursor-grabbing active:bg-accent"
                        style={{ left: `${100 - rightPct}%` }}
                        onPointerDown={onPointerDown('end')}
                    />
                </div>
            )}

            {/* Preset & shift buttons */}
            {hasRange && !disabled && (
                <div className="flex items-center gap-1.5">
                    <span className="mr-1 text-[10px] text-text-muted">Window:</span>
                    <PresetBtn label="1Y" onClick={() => setSpan(DAYS_1Y)} />
                    <PresetBtn label="2Y" onClick={() => setSpan(DAYS_2Y)} />
                    <div className="mx-1 h-3 w-px bg-border" />
                    <span className="mr-1 text-[10px] text-text-muted">Shift:</span>
                    <PresetBtn label="-2Y" onClick={() => shiftWindow(-DAYS_2Y)} />
                    <PresetBtn label="-1Y" onClick={() => shiftWindow(-DAYS_1Y)} />
                    <PresetBtn label="+1Y" onClick={() => shiftWindow(DAYS_1Y)} />
                    <PresetBtn label="+2Y" onClick={() => shiftWindow(DAYS_2Y)} />
                </div>
            )}
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
