import { useState } from "react";

interface StatCardProps {
  label: string;
  value: string;
  subValue?: string;
  tooltip?: string;
  color?: string;
}

export function StatCard({ label, value, subValue, tooltip, color }: StatCardProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div
      className="dashboard-card metric-card relative rounded-lg border border-border px-4 py-3 transition-colors hover:bg-bg-card-hover"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <div className="flex items-center gap-1.5">
        <span className="font-mono text-xs font-medium text-text-secondary">{label}</span>
        {tooltip && (
          <svg
            className="h-3 w-3 text-text-muted"
            viewBox="0 0 16 16"
            fill="currentColor"
          >
            <path d="M8 0a8 8 0 110 16A8 8 0 018 0zm.93 4.78a.75.75 0 00-1.36-.08l-.07.15-.01.07v.02a.76.76 0 00.06.28l.08.13.1.1.14.08.15.04h.02a.75.75 0 00.69-.48l.03-.14v-.17zm-.43 2.47a.75.75 0 00-1.49.13v3.87l.01.13a.75.75 0 001.49-.13V7.25l-.01-.13z" />
          </svg>
        )}
      </div>
      <div className="mt-1 font-mono text-xl font-semibold" style={{ color }}>
        {value}
      </div>
      {subValue && (
        <div className="mt-0.5 font-mono text-xs text-text-muted">{subValue}</div>
      )}

      {tooltip && showTooltip && (
        <div className="absolute left-1/2 bottom-full z-10 mb-2 -translate-x-1/2 rounded-md border border-border bg-bg-secondary px-3 py-2 font-mono text-xs text-text-secondary shadow-xl shadow-black/40 whitespace-nowrap">
          {tooltip}
          <div className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-bg-secondary" />
        </div>
      )}
    </div>
  );
}
